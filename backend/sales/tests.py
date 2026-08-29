import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import dns.resolver
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core import mail
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone, translation
from rest_framework.test import APIClient

from backend.testing import TempUploadsMixin
from catalog.models import Country, DocumentType, Product
from customer.models import Customer
from sales.models import Order, OrderItem, PaymentCallbackLog, Transaction
from sales.utils import send_purchases_link


class SalesFactoryMixin(TempUploadsMixin):
    """A catalogue small enough to reason about, and orders built the way the checkout builds them."""

    def make_product(self, name: str = "Germany utility bill 2022", price: str = "10.00", **overrides) -> Product:
        fields = {
            "name": name,
            "slug": overrides.pop("slug", name.lower().replace(" ", "-")),
            "country": self.country,
            "document_type": self.document_type,
            "year": 2022,
            "price": Decimal(price),
            "file": ContentFile(b"%PDF-1.4 test", name=f"{name}.psd"),
        }
        fields.update(overrides)
        return Product.objects.create(**fields)

    def make_item(self, product: Product, order: Order | None = None) -> OrderItem:
        return OrderItem.objects.create(
            order=order or self.order,
            product=product,
            product_name=product.name,
            unit_price=product.price,
        )

    def pay(self, order: Order | None = None):
        """Everything `apply_order_status` does for a paid invoice, without going through HTTP."""

        order = order or self.order
        order.status = Order.OrderStatus.PAID
        order.save(update_fields=["status"])
        order.mark_paid()
        return order.deliver()

    def setUp(self):
        super().setUp()
        self.country = Country.objects.create(name="Germany", slug="germany", code="de")
        self.document_type = DocumentType.objects.create(name="Utility bill", slug="utility-bill")
        self.customer = Customer.objects.create(email="buyer@example.com")
        self.order = Order.objects.create(customer=self.customer, total_price=Decimal("10.00"))


class DeliverTests(SalesFactoryMixin, TestCase):
    def test_deliver_issues_a_token_per_line(self):
        first = self.make_item(self.make_product("First", slug="first"))
        second = self.make_item(self.make_product("Second", slug="second"))

        self.order.deliver()

        for item in (first, second):
            item.refresh_from_db()
            self.assertTrue(item.is_token_valid())

    def test_deliver_is_idempotent_and_keeps_a_live_link(self):
        """A second callback must not invalidate the link the customer is already using."""

        item = self.make_item(self.make_product())
        self.order.deliver()
        item.refresh_from_db()
        token = item.token

        self.order.deliver()

        item.refresh_from_db()
        self.assertEqual(item.token, token)

    def test_deliver_replaces_an_expired_token(self):
        item = self.make_item(self.make_product())
        self.order.deliver()
        OrderItem.objects.filter(pk=item.pk).update(token_expires_at=timezone.now() - timedelta(seconds=1))

        self.order.deliver()

        item.refresh_from_db()
        self.assertTrue(item.is_token_valid())

    def test_a_product_cannot_be_bought_twice_in_one_order(self):
        product = self.make_product()
        self.make_item(product)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_item(product)


class OrderStateTests(SalesFactoryMixin, TestCase):
    def test_mark_paid_stamps_once(self):
        self.assertTrue(self.order.mark_paid())
        first = self.order.paid_at

        self.assertFalse(self.order.mark_paid())
        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_at, first)

    def test_reissuing_tokens_rotates_them(self):
        item = self.make_item(self.make_product())
        self.pay()
        item.refresh_from_db()
        first = item.token

        OrderItem.objects.filter(pk=item.pk).reissue_tokens()

        item.refresh_from_db()
        self.assertNotEqual(item.token, first)
        self.assertTrue(item.is_token_valid())

    def test_expired_token_is_invalid(self):
        item = self.make_item(self.make_product())
        self.pay()
        OrderItem.objects.filter(pk=item.pk).update(token_expires_at=timezone.now() - timedelta(seconds=1))

        item.refresh_from_db()
        self.assertFalse(item.is_token_valid())

    def test_only_paid_orders_are_downloadable(self):
        item = self.make_item(self.make_product())
        item.issue_token()

        self.assertNotIn(item, OrderItem.objects.downloadable())

        self.pay()
        self.assertIn(item, OrderItem.objects.downloadable())


def sign_plisio_payload(data: dict) -> dict:
    ordered_data = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    verify_hash = hmac.new(settings.PLISIO_SECRET_KEY.encode(), ordered_data.encode(), hashlib.sha1).hexdigest()
    return {**data, "verify_hash": verify_hash}


class PlisioCallbackTests(SalesFactoryMixin, TestCase):
    """The callback is the only thing Plisio ever tells us about an invoice."""

    def setUp(self):
        super().setUp()
        Site.objects.update_or_create(pk=1, defaults={"domain": "testserver", "name": "test"})

        self.item = self.make_item(self.make_product())
        self.client = APIClient()
        self.url = reverse("plisio-callback")
        self.payload = {
            "order_number": str(self.order.id),
            "status": "completed",
            "txn_id": "txn-1",
            "amount": "0.0005",
            "currency": "BTC",
            "merchant": "PsdShop",
            "merchant_id": "1",
            "comment": "",
        }

    def post_callback(self, **overrides):
        return self.client.post(self.url, sign_plisio_payload({**self.payload, **overrides}), format="json")

    def test_a_form_encoded_callback_is_accepted(self):
        # This is the shape Plisio actually posts. A QueryDict hands back lists, not strings, so
        # a callback read straight off request.data never matched its own hash - and every JSON
        # test above passed while production rejected the real thing.
        response = self.client.post(self.url, sign_plisio_payload(self.payload))

        self.assertEqual(response.status_code, 200, response.data)
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.paid_at)
        # The stored payload has to be readable too, not a dict of one-element lists.
        log = PaymentCallbackLog.objects.get()
        self.assertEqual(log.payload["status"], "completed")
        self.assertNotIn("verify_hash", log.payload)

    def test_paid_callback_delivers_and_emails_once(self):
        response = self.post_callback()

        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_token_valid())
        self.assertEqual(len(mail.outbox), 1)

    def test_duplicate_callback_is_absorbed(self):
        self.post_callback()
        response = self.post_callback()

        self.assertEqual(response.status_code, 200)
        # One e-mail, because paid_at is stamped exactly once.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_a_late_callback_still_delivers(self):
        """Nothing is reserved any more, so a payment after the invoice window is an ordinary sale."""

        Order.objects.filter(pk=self.order.pk).update(created_at=timezone.now() - timedelta(days=2))

        response = self.post_callback()

        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_token_valid())

    def test_currency_switch_keeps_both_invoices(self):
        self.post_callback(txn_id="txn-btc", status="cancelled duplicate")
        self.post_callback(txn_id="txn-eth", currency="ETH")

        self.assertEqual(Transaction.objects.filter(order=self.order).count(), 2)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.PAID)

    def test_every_callback_is_logged_without_the_hash(self):
        self.post_callback()

        log = PaymentCallbackLog.objects.get()
        self.assertEqual(log.order, self.order)
        self.assertNotIn("verify_hash", log.payload)

    def test_bad_hash_is_rejected(self):
        response = self.client.post(self.url, {**self.payload, "verify_hash": "nope"}, format="json")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(mail.outbox), 0)

    def test_unknown_order_is_logged_and_404(self):
        response = self.post_callback(order_number="999999")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(PaymentCallbackLog.objects.count(), 1)
        self.assertIsNone(PaymentCallbackLog.objects.get().order)

    def test_the_invoice_keeps_the_money_fields_plisio_sent(self):
        self.post_callback(
            source_amount="10.00",
            source_currency="USD",
            source_rate="0.00005",
            invoice_commission="0.0000025",
            confirmations="3",
        )

        txn = Transaction.objects.get()
        self.assertEqual(txn.source_amount, Decimal("10.00"))
        self.assertEqual(txn.source_currency, "USD")
        self.assertEqual(txn.source_rate, Decimal("0.00005"))
        self.assertEqual(txn.commission, Decimal("0.0000025"))
        self.assertEqual(txn.confirmations, 3)

    def test_a_later_callback_does_not_blank_what_an_earlier_one_filled(self):
        self.post_callback(status="pending", source_rate="0.00005", invoice_commission="0.0000025")
        self.post_callback(status="completed")

        txn = Transaction.objects.get()
        self.assertEqual(txn.source_rate, Decimal("0.00005"))
        self.assertEqual(txn.commission, Decimal("0.0000025"))

    def test_a_short_payment_is_delivered_but_says_so_in_the_log(self):
        with self.assertLogs("sales.views", level="WARNING") as logs:
            self.post_callback(status="mismatch", pending_amount="0.0001")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.OVERPAID)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_token_valid())
        self.assertTrue(any("short" in line for line in logs.output))

    def test_an_expired_invoice_only_moves_the_status(self):
        self.post_callback(status="expired")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.EXPIRED)
        self.assertIsNone(self.order.paid_at)
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_token_valid())


class ServedFilesMixin(SalesFactoryMixin):
    """Puts real bytes behind the product file, so a download can actually be streamed."""

    def setUp(self):
        super().setUp()

        product = self.make_product()
        path = self.private / product.file.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 test")

        self.item = self.make_item(product)
        self.pay()
        self.item.refresh_from_db()


class DownloadTests(ServedFilesMixin, TestCase):
    def download(self, token) -> int:
        return self.client.get(reverse("download-file", args=[token])).status_code

    def test_a_live_token_streams_the_file(self):
        response = self.client.get(reverse("download-file", args=[self.item.token]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 test")

    def test_expired_token_is_not_served(self):
        OrderItem.objects.filter(pk=self.item.pk).update(token_expires_at=timezone.now() - timedelta(seconds=1))

        self.assertEqual(self.download(self.item.token), 404)

    def test_unknown_token_is_not_served(self):
        self.assertEqual(self.download(uuid.uuid4()), 404)

    def test_a_line_of_an_unpaid_order_is_not_served(self):
        """`downloadable()` is keyed off the order being paid, not off the token existing."""

        Order.objects.filter(pk=self.order.pk).update(paid_at=None)

        self.assertEqual(self.download(self.item.token), 404)


class DownloadCounterTests(ServedFilesMixin, TestCase):
    def get_file(self, token=None):
        return self.client.get(reverse("download-file", args=[token or self.item.token]))

    def test_serving_the_file_counts_one_download(self):
        self.get_file()

        self.item.refresh_from_db()
        self.assertEqual(self.item.download_count, 1)
        self.assertIsNotNone(self.item.first_downloaded_at)

    def test_a_second_download_moves_only_the_last_stamp(self):
        self.get_file()
        self.item.refresh_from_db()
        first = self.item.first_downloaded_at

        self.get_file()

        self.item.refresh_from_db()
        self.assertEqual(self.item.download_count, 2)
        self.assertEqual(self.item.first_downloaded_at, first)
        self.assertGreaterEqual(self.item.last_downloaded_at, first)

    def test_a_refused_download_counts_nothing(self):
        OrderItem.objects.filter(pk=self.item.pk).update(token_expires_at=timezone.now() - timedelta(seconds=1))

        self.get_file()

        self.item.refresh_from_db()
        self.assertEqual(self.item.download_count, 0)

    def test_the_counter_survives_a_token_rotation(self):
        self.get_file()
        OrderItem.objects.filter(pk=self.item.pk).reissue_tokens()
        self.item.refresh_from_db()

        self.get_file()

        self.item.refresh_from_db()
        self.assertEqual(self.item.download_count, 2)

    def test_a_staff_member_looking_at_the_file_is_not_a_download(self):
        User.objects.create_superuser("root", "root@example.com", "pass")
        self.client.login(username="root", password="pass")

        with self.assertLogs("sales.views", level="INFO"):
            self.get_file()

        self.item.refresh_from_db()
        self.assertEqual(self.item.download_count, 0)

    def test_a_customer_still_counts_after_staff_looked(self):
        User.objects.create_superuser("root", "root@example.com", "pass")
        self.client.login(username="root", password="pass")
        with self.assertLogs("sales.views", level="INFO"):
            self.get_file()
        self.client.logout()

        self.get_file()

        self.item.refresh_from_db()
        self.assertEqual(self.item.download_count, 1)


class CheckoutTests(SalesFactoryMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product(price="12.50")
        self.other = self.make_product("Bank statement 2021", price="7.50", slug="bank-statement-2021")
        self.client = APIClient()
        self.url = reverse("order-create")

    def checkout(self, **overrides):
        payload = {"email": "new@example.com", "products": [self.product.pk], **overrides}
        return self.client.post(self.url, payload, format="json")

    @staticmethod
    def plisio_ok(url="https://plisio.net/invoice/1"):
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"status": "success", "data": {"invoice_url": url}}).encode()
        return response

    @staticmethod
    def plisio_error(message="No such currency", code=201):
        response = requests.Response()
        response.status_code = 400
        response._content = json.dumps({"status": "error", "data": {"message": message, "code": code}}).encode()
        return response

    def test_checkout_snapshots_name_and_price(self):
        with patch("sales.views.requests.get", return_value=self.plisio_ok()):
            response = self.checkout(products=[self.product.pk, self.other.pk])

        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(customer__email="new@example.com")
        self.assertEqual(order.total_price, Decimal("20.00"))
        self.assertEqual(
            sorted((item.product_name, item.unit_price) for item in order.items.all()),
            sorted([(self.product.name, Decimal("12.50")), (self.other.name, Decimal("7.50"))]),
        )

    def test_a_later_price_change_does_not_touch_the_order(self):
        with patch("sales.views.requests.get", return_value=self.plisio_ok()):
            self.checkout()

        self.product.price = Decimal("99.00")
        self.product.save(update_fields=["price"])

        order = Order.objects.get(customer__email="new@example.com")
        self.assertEqual(order.items.get().unit_price, Decimal("12.50"))
        self.assertEqual(order.total_price, Decimal("12.50"))

    def test_an_inactive_product_cannot_be_bought(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        response = self.checkout()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.filter(customer__email="new@example.com").exists())

    def test_a_failed_invoice_leaves_no_order_behind(self):
        with (
            patch("sales.views.requests.get", return_value=self.plisio_error()),
            self.assertLogs("sales.views", level="ERROR"),
        ):
            response = self.checkout()

        self.assertEqual(response.status_code, 502)
        self.assertFalse(Order.objects.filter(customer__email="new@example.com").exists())

    def test_a_failed_invoice_passes_the_provider_reason_on(self):
        with (
            patch("sales.views.requests.get", return_value=self.plisio_error("Currency is disabled", 202)),
            self.assertLogs("sales.views", level="ERROR"),
        ):
            response = self.checkout()

        self.assertEqual(response.data["detail"], "Currency is disabled")
        self.assertEqual(response.data["code"], "invoice_failed")
        self.assertEqual(response.data["provider_code"], 202)

    def test_unreachable_plisio_is_a_502_and_not_a_crash(self):
        with (
            patch("sales.views.requests.get", side_effect=requests.ConnectionError("boom")),
            self.assertLogs("sales.views", level="ERROR"),
        ):
            response = self.checkout()

        self.assertEqual(response.status_code, 502)
        self.assertFalse(Order.objects.filter(customer__email="new@example.com").exists())

    def test_a_network_error_never_writes_the_api_key_into_the_log(self):
        # requests puts the whole request URL in its exception message, and the key travels in it.
        leak = requests.ConnectionError(
            f"HTTPSConnectionPool: /api/v1/invoices/new?api_key={settings.PLISIO_SECRET_KEY}&order_number=1"
        )

        with (
            patch("sales.views.requests.get", side_effect=leak),
            self.assertLogs("sales.views", level="ERROR") as logs,
        ):
            response = self.checkout()

        self.assertEqual(response.status_code, 502)
        self.assertNotIn(settings.PLISIO_SECRET_KEY, "\n".join(logs.output))
        self.assertIn("***", "\n".join(logs.output))

    def test_checkout_remembers_the_site_language(self):
        with patch("sales.views.requests.get", return_value=self.plisio_ok()):
            self.checkout(language="ru")

        self.assertEqual(Customer.objects.get(email="new@example.com").language, "ru")

    def test_the_invoice_is_opened_in_the_customers_language(self):
        with patch("sales.views.requests.get", return_value=self.plisio_ok()) as request:
            self.checkout(language="ru")

        self.assertEqual(request.call_args.kwargs["params"]["language"], "ru_RU")

    def test_checkout_rejects_a_language_the_site_does_not_speak(self):
        response = self.checkout(language="de")

        self.assertEqual(response.status_code, 400)


class CheckoutLimitTests(SalesFactoryMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product()
        self.client = APIClient()
        self.url = reverse("order-create")

    def test_an_undeliverable_email_domain_is_rejected(self):
        with patch("customer.validators.dns.resolver.resolve", side_effect=dns.resolver.NXDOMAIN):
            response = self.client.post(
                self.url,
                {"email": "buyer@nope.invalid", "products": [self.product.pk]},
                format="json",
            )

        self.assertEqual(response.status_code, 400)

    def test_empty_order_is_rejected(self):
        response = self.client.post(self.url, {"email": "a@example.com", "products": []}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_too_many_products_are_rejected(self):
        ids = list(range(1, settings.MAX_ORDER_ITEMS + 2))

        response = self.client.post(self.url, {"email": "a@example.com", "products": ids}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_the_same_product_twice_is_rejected(self):
        response = self.client.post(
            self.url,
            {"email": "a@example.com", "products": [self.product.pk, self.product.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)


class CheckoutReuseTests(SalesFactoryMixin, TestCase):
    """A double click must not mint a second invoice for the same cart."""

    def setUp(self):
        super().setUp()
        self.product = self.make_product(price="12.50")
        self.other = self.make_product("Bank statement 2021", price="7.50", slug="bank-statement-2021")
        self.client = APIClient()
        self.url = reverse("order-create")
        self.invoice = "https://plisio.net/invoice/first"

    def first_checkout(self, **overrides):
        with patch("sales.views.requests.get", return_value=CheckoutTests.plisio_ok(self.invoice)):
            return self.client.post(
                self.url,
                {"email": "new@example.com", "products": [self.product.pk], **overrides},
                format="json",
            )

    def second_checkout(self, **overrides):
        with patch("sales.views.requests.get", return_value=CheckoutTests.plisio_ok("https://plisio.net/second")):
            return self.client.post(
                self.url,
                {"email": "new@example.com", "products": [self.product.pk], **overrides},
                format="json",
            )

    def test_second_checkout_returns_the_first_invoice(self):
        self.first_checkout()

        response = self.second_checkout()

        self.assertEqual(response.data["redirect_url"], self.invoice)
        self.assertEqual(Order.objects.filter(customer__email="new@example.com").count(), 1)

    def test_a_different_cart_gets_its_own_order(self):
        self.first_checkout()

        self.second_checkout(products=[self.product.pk, self.other.pk])

        self.assertEqual(Order.objects.filter(customer__email="new@example.com").count(), 2)

    def test_a_changed_price_gets_its_own_order(self):
        self.first_checkout()
        self.product.price = Decimal("20.00")
        self.product.save(update_fields=["price"])

        self.second_checkout()

        self.assertEqual(Order.objects.filter(customer__email="new@example.com").count(), 2)

    def test_an_expired_order_is_not_reused(self):
        self.first_checkout()
        order = Order.objects.get(customer__email="new@example.com")
        Order.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(days=1),
            updated_at=timezone.now() - timedelta(days=1),
        )

        self.second_checkout()

        self.assertEqual(Order.objects.filter(customer__email="new@example.com").count(), 2)

    def test_another_customer_does_not_reuse_the_invoice(self):
        self.first_checkout()

        with patch("sales.views.requests.get", return_value=CheckoutTests.plisio_ok("https://plisio.net/other")):
            response = self.client.post(
                self.url,
                {"email": "other@example.com", "products": [self.product.pk]},
                format="json",
            )

        self.assertEqual(response.data["redirect_url"], "https://plisio.net/other")

    def test_a_failed_invoice_leaves_nothing_to_reuse(self):
        with (
            patch("sales.views.requests.get", return_value=CheckoutTests.plisio_error()),
            self.assertLogs("sales.views", level="ERROR"),
        ):
            self.client.post(self.url, {"email": "new@example.com", "products": [self.product.pk]}, format="json")

        response = self.second_checkout()

        self.assertEqual(response.data["redirect_url"], "https://plisio.net/second")


class PurchasesMailTests(SalesFactoryMixin, TestCase):
    def setUp(self):
        super().setUp()
        Site.objects.update_or_create(pk=1, defaults={"domain": "testserver", "name": "test"})
        self.make_item(self.make_product())
        self.pay()
        self.customer.rotate_access_token()

    def test_the_mail_carries_the_purchases_link_and_nothing_else(self):
        send_purchases_link(RequestFactory().get("/"), self.customer)

        body = mail.outbox[0].body
        self.assertIn(str(self.customer.access_token), body)
        self.assertNotIn("/api/files/", body)

    def test_the_mail_follows_the_customers_language(self):
        self.customer.set_language("ru")

        with translation.override("en"):
            send_purchases_link(RequestFactory().get("/"), self.customer)

        self.assertNotEqual(mail.outbox[0].subject, "")
        self.assertEqual(mail.outbox[0].to, [self.customer.email])

    def test_the_link_opens_the_page_in_the_customers_language(self):
        """The language is a path prefix, and the browser that will open the link is not here."""

        self.customer.set_language("ru")

        with translation.override("en"):
            send_purchases_link(RequestFactory().get("/"), self.customer)

        self.assertIn(f"/ru/purchases/{self.customer.access_token}/", mail.outbox[0].body)


class SendDownloadLinksTests(SalesFactoryMixin, TestCase):
    def setUp(self):
        super().setUp()
        Site.objects.update_or_create(pk=1, defaults={"domain": "testserver", "name": "test"})

        self.item = self.make_item(self.make_product())
        self.pay()
        self.item.refresh_from_db()

        self.client = APIClient()
        self.url = reverse("send-links")

    def test_the_purchases_link_is_rotated_and_emailed(self):
        self.customer.rotate_access_token()
        old_token = self.customer.access_token

        response = self.client.post(self.url, {"email": self.customer.email}, format="json")

        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertNotEqual(self.customer.access_token, old_token)
        self.assertEqual(len(mail.outbox), 1)

    def test_file_tokens_survive_a_rotation(self):
        """Links the customer has already shared must keep working - only the page link is revoked."""

        self.client.post(self.url, {"email": self.customer.email}, format="json")

        token = self.item.token
        self.item.refresh_from_db()
        self.assertEqual(self.item.token, token)

    def test_an_undelivered_paid_line_is_topped_up(self):
        OrderItem.objects.filter(pk=self.item.pk).update(token=None, token_expires_at=None)

        self.client.post(self.url, {"email": self.customer.email}, format="json")

        self.item.refresh_from_db()
        self.assertTrue(self.item.is_token_valid())

    def test_unknown_email_is_404(self):
        response = self.client.post(self.url, {"email": "nobody@example.com"}, format="json")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_paid_order_whose_status_moved_on_is_still_served(self):
        self.order.status = Order.OrderStatus.PENDING
        self.order.save(update_fields=["status"])

        response = self.client.post(self.url, {"email": self.customer.email}, format="json")

        self.assertEqual(response.status_code, 200)


class PurchasesPageTests(SalesFactoryMixin, TestCase):
    """The token in the URL is the whole authentication, so its edges are the security boundary."""

    def setUp(self):
        super().setUp()
        Site.objects.update_or_create(pk=1, defaults={"domain": "testserver", "name": "test"})

        self.product = self.make_product()
        self.item = self.make_item(self.product)
        self.pay()
        self.item.refresh_from_db()

        self.customer.rotate_access_token()
        self.client = APIClient()

    def page(self, token=None):
        return self.client.get(reverse("purchases", args=[token or self.customer.access_token]))

    def test_the_page_lists_paid_orders_with_their_files(self):
        response = self.page()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], self.customer.email)
        self.assertEqual(len(response.data["orders"]), 1)

        item = response.data["orders"][0]["items"][0]
        self.assertEqual(item["product_name"], self.product.name)
        self.assertTrue(item["is_downloadable"])
        self.assertIn("/api/files/", item["download_url"])

    def test_an_unpaid_order_is_not_listed(self):
        pending = Order.objects.create(customer=self.customer, total_price=Decimal("10.00"))
        self.make_item(self.make_product("Another", slug="another"), order=pending)

        response = self.page()

        self.assertEqual(len(response.data["orders"]), 1)
        self.assertEqual(response.data["orders"][0]["id"], self.order.id)

    def test_an_expired_token_is_404_and_says_nothing(self):
        self.customer.access_token_expires_at = timezone.now() - timedelta(seconds=1)
        self.customer.save(update_fields=["access_token_expires_at"])

        response = self.page()

        self.assertEqual(response.status_code, 404)
        self.assertNotIn(self.customer.email, str(response.data))

    def test_an_unknown_token_answers_exactly_like_an_expired_one(self):
        self.customer.access_token_expires_at = timezone.now() - timedelta(seconds=1)
        self.customer.save(update_fields=["access_token_expires_at"])
        expired = self.page().data

        self.assertEqual(self.page(uuid.uuid4()).data, expired)

    def test_a_paid_order_whose_status_moved_on_is_still_listed(self):
        """
        Switching cryptocurrency leaves a `cancelled duplicate` callback for the invoice the
        customer walked away from, and that maps back to PENDING. `paid_at` is what was paid.
        """

        self.order.status = Order.OrderStatus.PENDING
        self.order.save(update_fields=["status"])

        response = self.page()

        self.assertEqual(len(response.data["orders"]), 1)

    def test_an_expired_file_token_offers_no_url(self):
        OrderItem.objects.update(token_expires_at=timezone.now() - timedelta(seconds=1))

        item = self.page().data["orders"][0]["items"][0]

        self.assertFalse(item["is_downloadable"])
        self.assertIsNone(item["download_url"])


class RefreshTokenTests(SalesFactoryMixin, TestCase):
    def setUp(self):
        super().setUp()
        Site.objects.update_or_create(pk=1, defaults={"domain": "testserver", "name": "test"})

        self.first = self.make_item(self.make_product("First", slug="first"))
        self.second = self.make_item(self.make_product("Second", slug="second"))
        self.pay()
        self.first.refresh_from_db()
        self.second.refresh_from_db()

        self.customer.rotate_access_token()
        self.client = APIClient()

    def refresh(self, item_id, token=None):
        url = reverse("purchases-refresh", args=[token or self.customer.access_token, item_id])
        return self.client.post(url)

    def test_refreshing_one_file_leaves_the_others_alone(self):
        old_second = self.second.token

        response = self.refresh(self.first.pk)

        self.assertEqual(response.status_code, 200)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertNotEqual(self.first.token, response.data["download_url"].rsplit("/", 2)[-2])
        self.assertEqual(self.second.token, old_second)

    def test_refresh_all_rotates_every_file(self):
        before = {self.first.pk: self.first.token, self.second.pk: self.second.token}

        response = self.client.post(reverse("purchases-refresh-all", args=[self.customer.access_token]))

        self.assertEqual(response.status_code, 200)
        for item in (self.first, self.second):
            item.refresh_from_db()
            self.assertNotEqual(item.token, before[item.pk])

    def test_somebody_elses_file_cannot_be_refreshed(self):
        stranger = Customer.objects.create(email="stranger@example.com")
        stranger_order = Order.objects.create(customer=stranger, total_price=Decimal("10.00"))
        theirs = self.make_item(self.make_product("Theirs", slug="theirs"), order=stranger_order)
        self.pay(stranger_order)
        theirs.refresh_from_db()

        response = self.refresh(theirs.pk)

        self.assertEqual(response.status_code, 404)
        token = theirs.token
        theirs.refresh_from_db()
        self.assertEqual(theirs.token, token)

    def test_an_expired_page_token_refreshes_nothing(self):
        self.customer.access_token_expires_at = timezone.now() - timedelta(seconds=1)
        self.customer.save(update_fields=["access_token_expires_at"])

        response = self.refresh(self.first.pk)

        self.assertEqual(response.status_code, 404)


class CartItemsTests(SalesFactoryMixin, TestCase):
    """The cart lives in the browser, so the page asks the server what those ids are."""

    def setUp(self):
        super().setUp()
        self.product = self.make_product(price="12.50")
        self.hidden = self.make_product("Hidden", slug="hidden", is_active=False)
        self.client = APIClient()

    def items(self, ids: str):
        return self.client.get(reverse("cart-items"), {"ids": ids})

    def test_known_ids_come_back_priced(self):
        response = self.items(str(self.product.pk))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name_en"], self.product.name)
        self.assertEqual(Decimal(response.data[0]["price"]), Decimal("12.50"))

    def test_an_inactive_product_is_simply_absent(self):
        response = self.items(f"{self.product.pk},{self.hidden.pk}")

        self.assertEqual([row["id"] for row in response.data], [self.product.pk])

    def test_garbage_ids_are_ignored(self):
        response = self.items("nope,,7.5,-3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_both_languages_ride_along(self):
        """No `?lang=` anywhere in the API (ADR-0010): every visitor gets the same payload."""

        self.product.name_ru = "Счёт за коммуналку"
        self.product.save(update_fields=["name_ru"])

        response = self.client.get(reverse("cart-items"), {"ids": str(self.product.pk), "lang": "ru"})

        self.assertEqual(response.data[0]["name_ru"], "Счёт за коммуналку")
        self.assertEqual(response.data[0]["name_en"], self.product.name)

    def test_a_line_carries_what_the_grid_card_carries(self):
        """The cart draws the same card the catalog does, so it needs the same fields."""

        row = self.items(str(self.product.pk)).data[0]

        self.assertEqual(
            set(row),
            {"id", "url_slug", "name_en", "name_ru", "price", "year", "country", "document_type", "preview"},
        )


class MailOutageTests(SalesFactoryMixin, TestCase):
    """A dead SMTP must not cost the customer their order or their link."""

    def setUp(self):
        super().setUp()
        Site.objects.update_or_create(pk=1, defaults={"domain": "testserver", "name": "test"})

        self.item = self.make_item(self.make_product())
        self.client = APIClient()

    def test_a_paid_order_is_still_delivered_when_the_mail_fails(self):
        payload = sign_plisio_payload(
            {
                "order_number": str(self.order.id),
                "txn_id": "txn-mail-outage",
                "status": "completed",
                "amount": "0.001",
                "currency": "BTC",
                "source_currency": "USD",
                "source_amount": "10.00",
            }
        )

        with (
            patch("sales.views.send_purchases_link", side_effect=OSError("smtp is down")),
            self.assertLogs("sales.views", level="ERROR"),
        ):
            response = self.client.post(reverse("plisio-callback"), payload, format="json")

        # 200, so Plisio stops retrying: a retry would deliver nothing new anyway.
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.OrderStatus.PAID)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_token_valid())

    def test_the_form_says_so_instead_of_pretending_the_mail_went_out(self):
        self.pay()

        with (
            patch("sales.views.send_purchases_link", side_effect=OSError("smtp is down")),
            self.assertLogs("sales.views", level="ERROR"),
        ):
            response = self.client.post(reverse("send-links"), {"email": self.customer.email}, format="json")

        self.assertEqual(response.status_code, 502)


class PruneCallbackLogsTests(SalesFactoryMixin, TestCase):
    """The raw payloads are for debugging a sale, not for keeping forever."""

    def make_log(self, age_days: int) -> PaymentCallbackLog:
        log = PaymentCallbackLog.objects.create(order=self.order, txn_id=f"txn-{age_days}", payload={})
        # auto_now_add wins over anything passed to create(), so the date is set afterwards.
        PaymentCallbackLog.objects.filter(pk=log.pk).update(received_at=timezone.now() - timedelta(days=age_days))
        return log

    def test_only_the_logs_past_the_window_go(self):
        self.make_log(400)
        self.make_log(10)

        call_command("prune_callback_logs", days=180, skip_checks=False)

        self.assertEqual([log.txn_id for log in PaymentCallbackLog.objects.all()], ["txn-10"])

    def test_a_dry_run_deletes_nothing(self):
        self.make_log(400)

        call_command("prune_callback_logs", days=180, dry_run=True, skip_checks=False)

        self.assertEqual(PaymentCallbackLog.objects.count(), 1)

    def test_it_refuses_to_empty_the_table(self):
        self.make_log(0)

        call_command("prune_callback_logs", days=0, stderr=StringIO(), skip_checks=False)

        self.assertEqual(PaymentCallbackLog.objects.count(), 1)
