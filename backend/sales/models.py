import logging
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db.models import F, UniqueConstraint, Value
from django.db.models.functions import Coalesce
from django.db.transaction import atomic
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from backend.sites import absolute_url
from catalog.models import Product

logger = logging.getLogger(__name__)


class OrderQuerySet(models.QuerySet):
    def paid(self) -> "OrderQuerySet":
        """
        Orders the customer has actually paid for - the only definition, see `CustomerQuerySet`.

        Keyed off `paid_at` and not off `status`: the stamp is written exactly once by
        `mark_paid()`, while the status keeps moving with every callback. Plisio reports the
        invoice a customer abandoned when switching coin as `cancelled duplicate`, which maps back
        to PENDING - filtering by status would drop a delivered order off the purchases page.
        """

        return self.filter(paid_at__isnull=False)

    def reusable(self, email: str, products: list[Product]) -> "Order | None":
        """
        A live invoice of this customer for exactly this cart, or None.

        Handing it back instead of minting a second order is what keeps a double click - or someone
        probing the checkout with the same cart - from filling Plisio with dead invoices.

        Both halves of the filter carry weight. `paid_at` is the paid test, because a late
        `cancelled duplicate` callback after the `completed` one puts a settled order back at
        PENDING (`plisio.apply_order_status`) and would otherwise hand its dead invoice to the next
        checkout. `status` is what excludes the invoices Plisio has already killed - EXPIRED,
        CANCELLED, ERROR - which `paid_at` alone would let through.
        """

        wanted = sorted(product.pk for product in products)

        candidates = (
            self.filter(customer__email=email, status=Order.OrderStatus.PENDING, paid_at__isnull=True)
            .exclude(invoice_url="")
            .prefetch_related("items__product")
            .order_by("-created_at")
        )

        for order in candidates:
            if order.is_expired():
                continue

            items_of = list(order.items.all())
            if sorted(item.product_id for item in items_of) != wanted:
                continue

            # The catalog price must not have moved since, otherwise the old invoice would sell at
            # the old price. Both sides come from the same column, so this compares exactly.
            if all(item.unit_price == item.product.price for item in items_of):
                return order

        return None


class Order(models.Model):
    """
    One checkout: what the customer asked for and how the payment went.

    :param customer: Who bought.
    :param status: Order status (PENDING, PAID, OVERPAID, EXPIRED, ERROR, CANCELLED).
    :param total_price: Total price of the order in USD, as sent to Plisio.
    :param invoice_url: Plisio invoice this order was sent to, empty until the invoice is minted.
    :param created_at: When the order was created.
    :param updated_at: When the order was last touched.
    :param paid_at: When the order first became paid; stamped once, gates the delivery email.
    """

    class OrderStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        OVERPAID = "OVERPAID", "Overpaid"
        EXPIRED = "EXPIRED", "Expired"
        ERROR = "ERROR", "Error"
        CANCELLED = "CANCELLED", "Cancelled"

    # How long an unpaid order can still be sent back to its own invoice. The invoice Plisio mints
    # expires in 60 minutes, so an order gets that from its last move plus ten minutes of grace
    # from creation. Read these instead of writing the number again - `statistics.time_to_pay`
    # counts late payments against them.
    INVOICE_FROM_CREATED = timedelta(hours=1, minutes=10)
    INVOICE_FROM_UPDATED = timedelta(hours=1)

    customer = models.ForeignKey("customer.Customer", related_name="orders", on_delete=models.PROTECT)
    status = models.CharField(max_length=15, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    invoice_url = models.URLField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    objects = OrderQuerySet.as_manager()

    if TYPE_CHECKING:
        items: "OrderItemQuerySet"
        transactions: models.QuerySet["Transaction"]
        callback_logs: models.QuerySet["PaymentCallbackLog"]

    class Meta:
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.id} - {self.customer.email if self.customer_id else 'NULL'}"

    def is_expired(self):
        now = timezone.now()

        return now > self.created_at + self.INVOICE_FROM_CREATED or now > self.updated_at + self.INVOICE_FROM_UPDATED

    def mark_paid(self) -> bool:
        """
        Stamp paid_at, but only the first time.

        One UPDATE decides it, so a duplicate Plisio callback loses the race instead of sending a
        second email - the delivery itself is idempotent anyway.
        """

        now = timezone.now()
        stamped = Order.objects.filter(pk=self.pk, paid_at__isnull=True).update(paid_at=now)
        if stamped:
            self.paid_at = now
            logger.info(f"Order {self.pk} marked as paid at {now:%Y-%m-%d %H:%M:%S}")
        else:
            # No timestamp in the message: the loser of the race is holding an instance from
            # before the winning UPDATE, so `self.paid_at` here is whatever it was loaded with -
            # usually None, which read as "already paid at None".
            logger.info(f"Order {self.pk} was already paid, not sending a second email")

        return bool(stamped)

    @atomic
    def deliver(self) -> list["OrderItem"]:
        """
        Hand the files over: every line gets a download token.

        A template never runs out (docs/architecture.md), so this cannot fail on stock, and repeating it is
        harmless - a line that already holds a live token keeps it, so a second callback does not
        invalidate the link the customer is already using.
        """

        items = list(self.items.select_for_update())
        fresh = [item for item in items if not item.is_token_valid()]

        for item in fresh:
            item.issue_token(commit=False)

        if fresh:
            OrderItem.objects.bulk_update(fresh, ["token", "token_expires_at"])
            logger.info(f"Order {self.pk} delivered lines {[item.pk for item in fresh]}")

        return items


class OrderItemQuerySet(models.QuerySet):
    def downloadable(self) -> "OrderItemQuerySet":
        """Lines of paid orders - the only ones the purchases page lists and serves."""

        return self.filter(order__paid_at__isnull=False)

    def of_customer(self, customer) -> "OrderItemQuerySet":
        return self.filter(order__customer=customer)

    @atomic
    def reissue_tokens(self) -> list["OrderItem"]:
        """Give every selected line a fresh token, resetting DOWNLOAD_TTL. Idempotent by nature."""

        items = list(self.select_for_update())
        for item in items:
            item.issue_token(commit=False)

        OrderItem.objects.bulk_update(items, ["token", "token_expires_at"])
        return items


class OrderItem(models.Model):
    """
    One product in an order, priced as of checkout, and the link it is downloaded from.

    The snapshot fields answer "what did this cost back then" - the catalog is free to change
    afterwards. There is no quantity: buying the same template twice makes no sense, so a product
    appears in an order at most once (docs/architecture.md).

    :param order: Order this line belongs to.
    :param product: Product bought; PROTECT, because the file has to outlive the sale.
    :param product_name: Product name as of checkout.
    :param unit_price: Price as of checkout, in USD.
    :param token: Opens this one file; rotated on request, see DOWNLOAD_TTL.
    :param token_expires_at: When the token stops working.
    :param download_count: How many times the file was served to the customer.
    :param first_downloaded_at: When the customer first took the file.
    :param last_downloaded_at: When the customer last took the file.
    """

    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="order_items", on_delete=models.PROTECT)

    product_name = models.CharField(max_length=255)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    token = models.UUIDField(null=True, blank=True, unique=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)

    # Written only by `record_download`, which is the one place a download touches the database.
    download_count = models.PositiveIntegerField(default=0)
    first_downloaded_at = models.DateTimeField(null=True, blank=True)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)

    objects = OrderItemQuerySet.as_manager()

    class Meta:
        verbose_name = _("Order item")
        verbose_name_plural = _("Order items")
        ordering = ["pk"]
        constraints = [
            UniqueConstraint(fields=["order", "product"], name="one_line_per_product_in_order"),
        ]

    def __str__(self):
        return f"{self.product_name} - {self.order}"

    def is_token_valid(self) -> bool:
        return self.token is not None and self.token_expires_at is not None and timezone.now() <= self.token_expires_at

    def issue_token(self, commit: bool = True):
        """Mint a new download token and reset its TTL, killing the previous one."""

        self.token = uuid.uuid4()
        self.token_expires_at = timezone.now() + settings.DOWNLOAD_TTL
        if commit:
            self.save(update_fields=["token", "token_expires_at"])

    def record_download(self):
        """
        Count one served download.

        An UPDATE with F() rather than a save(): two browsers pulling the same link at once must
        add up to two, and nothing else on the row may be written back from a stale instance.
        """

        now = timezone.now()
        OrderItem.objects.filter(pk=self.pk).update(
            download_count=F("download_count") + 1,
            first_downloaded_at=Coalesce("first_downloaded_at", Value(now)),
            last_downloaded_at=now,
        )

    def get_download_url(self, request: HttpRequest | None) -> str:
        """
        Absolute link to this one file.

        The token alone identifies it - the e-mail used to be part of the path and proved nothing,
        since it travelled in the same message as the token.
        """

        return absolute_url(reverse("download-file", args=[self.token]), request)


class Transaction(models.Model):
    # noinspection GrazieInspection
    """
    One Plisio invoice of an order.

    An order can have several: switching cryptocurrency mints a new invoice with a new txn_id while
    order_number stays ours, so this is a FK and not a OneToOne (docs/architecture.md).

    :param order: Order being paid for.
    :param txn_id: Plisio invoice id.
    :param amount: Amount in the invoice's cryptocurrency.
    :param currency: Cryptocurrency of the invoice.
    :param pending_amount: What is still missing when the customer underpaid.
    :param tx_urls: Blockchain transactions of this invoice, as sent by Plisio.
    :param source_amount: The fiat side of the invoice, as Plisio reports it.
    :param source_currency: Currency of `source_amount`; ours is always USD (docs/architecture.md).
    :param source_rate: How much of `currency` one unit of `source_currency` buys, so that
        `amount / source_rate` is the fiat value. It divides, it never multiplies - Plisio's own
        example has 0.0104 ETH at a rate of 0.00052 for $20.
    :param commission: What Plisio kept, quoted in the invoice's cryptocurrency, not in fiat.
    :param status: Status of the invoice: new, pending, pending internal, expired, completed,
        mismatch, error, cancelled, cancelled duplicate.
    :param confirmations: Number of confirmations of the crypto transaction.
    :param created_at: When we first saw the invoice.
    :param updated_at: When we last got a callback about it.
    :param merchant: Merchant name (from api settings).
    :param merchant_id: Merchant ID (from api settings).
    :param comment: Invoice comment (if provided).
    """

    class TransactionStatus(models.TextChoices):
        NEW = "new", "New"
        PENDING = "pending", "Pending"
        PENDING_INTERNAL = "pending internal", "Pending Internal"
        EXPIRED = "expired", "Expired"
        COMPLETED = "completed", "Completed"
        MISMATCH = "mismatch", "Mismatch"
        ERROR = "error", "Error"
        CANCELLED = "cancelled", "Cancelled"
        CANCELLED_DUPLICATE = "cancelled duplicate", "Cancelled Duplicate"

    order = models.ForeignKey(Order, related_name="transactions", on_delete=models.CASCADE)
    txn_id = models.CharField(max_length=100, unique=True)

    amount = models.DecimalField(max_digits=20, decimal_places=10)
    currency = models.CharField(max_length=10)

    pending_amount = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)
    tx_urls = models.JSONField(null=True, blank=True)

    source_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    source_currency = models.CharField(max_length=10, blank=True, default="")
    source_rate = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)
    commission = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)

    status = models.CharField(max_length=30, choices=TransactionStatus.choices, default=TransactionStatus.NEW)
    confirmations = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    merchant = models.CharField(max_length=127, null=True, blank=True)
    merchant_id = models.CharField(max_length=63, null=True, blank=True)
    comment = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Transaction {self.txn_id} - order {self.order_id}"


class PaymentCallbackLog(models.Model):
    """
    Raw Plisio callback, exactly as it arrived.

    Written after the hash check but before the atomic block, so a rolled-back callback still
    leaves a trace - the old schema overwrote invoice history and left nothing to debug with.

    :param order: Order the callback claims to be about, NULL if we could not find one.
    :param txn_id: Plisio invoice id from the payload.
    :param payload: The payload itself, minus verify_hash.
    :param received_at: When it arrived.
    """

    order = models.ForeignKey(Order, related_name="callback_logs", on_delete=models.SET_NULL, null=True, blank=True)
    txn_id = models.CharField(max_length=100, null=True, blank=True)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Payment callback")
        verbose_name_plural = _("Payment callbacks")
        ordering = ["-received_at"]

    def __str__(self):
        return f"Callback {self.txn_id or '?'} at {self.received_at:%Y-%m-%d %H:%M:%S}"
