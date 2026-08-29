import hashlib
import hmac
import json
import logging

import requests
from django import views
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, HttpResponseNotFound
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product
from catalog.serializers import ProductListSerializer
from customer.models import Customer
from sales.models import Order, OrderItem, PaymentCallbackLog, Transaction
from sales.plisio import apply_order_status, callback_to_fields
from sales.serializers import (
    OrderSerializer,
    PurchaseItemSerializer,
    PurchaseOrderSerializer,
    SendDownloadLinksSerializer,
)
from sales.utils import send_purchases_link

logger = logging.getLogger(__name__)

# Our language codes -> the locales Plisio names its checkout in. Anything else falls back to en_US.
PLISIO_LANGUAGES = {
    "en": "en_US",
    "ru": "ru_RU",
}


def redact(value) -> str:
    """Message with the Plisio API key blanked out - it rides in the request URL requests echoes."""

    return str(value).replace(settings.PLISIO_SECRET_KEY, "***")


class OrderCreateView(APIView):
    """Create a new order endpoint"""

    def post(self, request, *args, **kwargs):
        serializer = OrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = serializer.save()
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if serializer.reused_order is not None:
            # Same customer, same cart, invoice still alive: send them back to it instead of
            # minting a second invoice for the same purchase.
            logger.info(f"Order {order.id} reused for a repeated checkout")
            return Response({"redirect_url": order.invoice_url}, status=status.HTTP_201_CREATED)

        # Prepare data for plisio invoice
        invoice_data = {
            "order_name": f"Order {order.id}",
            "order_number": order.id,
            "source_currency": "USD",
            "source_amount": order.total_price,
            "email": order.customer.email,
            "api_key": settings.PLISIO_SECRET_KEY,
            "language": PLISIO_LANGUAGES.get(order.customer.language, "en_US"),
            "expire_min": "60",
        }

        response, payload = None, {}
        try:
            response = requests.get("https://plisio.net/api/v1/invoices/new", params=invoice_data, timeout=30)
            payload = response.json()
        except ValueError as e:
            # Includes requests' JSONDecodeError - the call went through, the body is not JSON.
            logger.error(f"Plisio answered order {order.id} with something that is not JSON: {redact(e)}")
        except requests.RequestException as e:
            # requests puts the request URL in the message, and the API key travels in it.
            logger.error(f"Plisio is unreachable for order {order.id}: {redact(e)}")

        if response is not None and response.status_code == 200 and payload.get("status") == "success":
            logger.info(f"Order {order.id} created successfully")
            redirect_url = payload["data"]["invoice_url"]

            # Stored so a repeated checkout of the same cart can be sent back to this invoice.
            order.invoice_url = redirect_url
            order.save(update_fields=["invoice_url"])

            return Response({"redirect_url": redirect_url}, status=status.HTTP_201_CREATED)

        # Plisio puts its own diagnosis in data.{message,code}; pass it on so the storefront can say
        # more than "something went wrong", and log the raw answer for us.
        error = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        http_status = response.status_code if response is not None else None
        logger.error(f"Invoice not created for order {order.id}: HTTP {http_status}, payload {payload}")

        # Nothing was handed over and no invoice exists, so the order is just noise - drop it.
        order.delete()

        return Response(
            {
                "detail": error.get("message") or "Error creating invoice",
                "code": "invoice_failed",
                "provider_code": error.get("code"),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )


class PlisioCallbackView(APIView):
    """Endpoint for plisio callback"""

    @staticmethod
    def validate_hash(data):
        received_hash = data.pop("verify_hash", None)

        ordered_data = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        calculated_hash = hmac.new(
            settings.PLISIO_SECRET_KEY.encode("utf-8"), ordered_data.encode("utf-8"), hashlib.sha1
        ).hexdigest()

        # Constant-time: a plain == leaks how many leading bytes matched, and the attacker
        # controls the value being compared.
        return hmac.compare_digest(calculated_hash, received_hash or "")

    def post(self, request, *args, **kwargs):
        # Plisio posts form-encoded, so request.data is a QueryDict: `copy()` keeps it one, and a
        # QueryDict hands back *lists* from pop() and from dict(). That is why this is flattened
        # first - the hash compare, the stored payload and callback_to_fields all want plain
        # strings, and a JSON post (what the tests do) already arrives as a plain dict.
        data = request.data.dict() if hasattr(request.data, "dict") else dict(request.data)
        if not self.validate_hash(data):
            logger.warning(f"Hash verification failed for transaction {data.get('txn_id')}")
            return Response(
                {"detail": "Invalid verify_hash"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        order = Order.objects.filter(id=data.get("order_number")).first()

        # Logged before the atomic block on purpose: a rolled-back callback still leaves a trace.
        # validate_hash() has already popped verify_hash, so no secret-derived value is stored.
        PaymentCallbackLog.objects.create(order=order, txn_id=data.get("txn_id"), payload=dict(data))

        if order is None:
            logger.warning(f"Callback for unknown order {data.get('order_number')}")
            return Response({"detail": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            self.upsert_transaction(order, data)
            first_payment, items = apply_order_status(order, data.get("status"))

        # A duplicate callback delivers nothing new and must not send a second email.
        if first_payment and items:
            customer = order.customer
            # Deliberately not a rotation: a second purchase must not revoke the link the customer
            # got with the first one and may still have open.
            customer.ensure_access_token()

            try:
                send_purchases_link(request, customer)
            except Exception as e:
                # The sale itself went through and the files are handed over - failing the
                # callback here would only make Plisio retry, and the retry sends nothing because
                # paid_at is already stamped. The customer gets their link from the form on the site.
                logger.error(f"Order {order.id} is delivered but the e-mail did not go out: {e}")

        return Response(
            {"detail": "Order and transaction status updated"},
            status=status.HTTP_200_OK,
        )

    def upsert_transaction(self, order: Order, data: dict) -> Transaction:
        """Store the invoice this callback is about. The order itself moves in `apply_order_status`."""

        update_data = {"order": order, **callback_to_fields(data)}

        # Keyed by txn_id, not by order: switching cryptocurrency mints a new invoice for the same
        # order, and the old schema overwrote the previous one. A payload without an invoice id is
        # not expected - it gets a stable synthetic one instead of a second nameless row.
        txn_id = data.get("txn_id") or f"unknown-{order.id}"
        txn, _ = Transaction.objects.update_or_create(txn_id=txn_id, defaults=update_data)

        if txn.status == Transaction.TransactionStatus.MISMATCH and txn.pending_amount:
            # Plisio says "mismatch" whichever way the sum went, and we hand the files over either
            # way - refusing here would strand a customer whose payment Plisio accepted. A missing
            # amount is a sale to look at by hand, so it does not get to pass quietly.
            logger.warning(
                f"Order {order.id}: invoice {txn.txn_id} is short {txn.pending_amount} {txn.currency} "
                f"and was still delivered"
            )

        return txn


def serve_order_item(item: OrderItem, count: bool = True):
    """Stream the file behind one bought line, or 404 - never say which of the checks failed."""

    if not item.is_token_valid():
        return HttpResponseNotFound("Expired download link")

    if not item.product.file:
        logger.error(f"Order item {item.id} points at a product without a file")
        return HttpResponseNotFound()

    # noqa SIM115: FileResponse owns the handle and closes it when the stream ends - a `with` here
    # would close the file before a single byte went out.
    response = FileResponse(open(item.product.file.path, "rb"), as_attachment=True)  # noqa: SIM115
    if count:
        # Counted only once the file is actually open, so a 404 above never looks like a download.
        item.record_download()
    return response


class DownloadFileView(views.View):
    """Download one delivered file by its token alone."""

    def get(self, request, *args, **kwargs):
        token = self.kwargs.get("uuid")
        if token is None:
            return HttpResponseNotFound()

        try:
            item = OrderItem.objects.select_related("product").downloadable().get(token=token)
        except (OrderItem.DoesNotExist, ValidationError, ValueError):
            return HttpResponseNotFound()

        # "Did the customer take the file" is what the counter answers, so the owner checking a file
        # from the admin must not move it. The check is on the session, not on the link: a staff
        # member who opens a real customer link while logged into the admin is not counted either.
        staff = request.user.is_authenticated and request.user.is_staff
        if staff:
            logger.info(f"Staff download of order item {item.id}, not counted")

        return serve_order_item(item, count=not staff)


class SendDownloadLinksView(APIView):
    """Refresh download links and send them to customer's email"""

    def post(self, request, *args, **kwargs):
        serializer = SendDownloadLinksSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        customer = Customer.objects.filter(email=email).first()
        orders = list(customer.orders.paid()) if customer else []

        if not orders:
            return HttpResponseNotFound()

        # They are asking from the site right now, so this is the language to answer in.
        customer.set_language(serializer.validated_data.get("language"))

        try:
            with transaction.atomic():
                for order in orders:
                    # Idempotent, and it tops up anything an old sale failed to hand over.
                    order.deliver()

                # This is the "revoke the old link" mechanism: whoever holds the previous purchases
                # URL loses it here. File tokens are left alone - the page refreshes them itself.
                customer.rotate_access_token()
        except ValueError as e:
            logger.warning(f"Cannot re-issue links for {email}: {e}")
            return Response({"detail": "Order processing conflict"}, status=status.HTTP_409_CONFLICT)

        try:
            send_purchases_link(request, customer)
        except Exception as e:
            # The token was already rotated, so the previous link is gone either way - the customer
            # has to be told to try again rather than left staring at a success message.
            logger.error(f"Cannot mail the purchases link to {email}: {e}")
            return Response({"detail": "Cannot send the e-mail right now"}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"detail": "The link is sent"}, status=status.HTTP_200_OK)


# One answer for an unknown, malformed or expired token: the page must not confirm that a token
# exists, and the customer's next step is the same either way.
PURCHASES_GONE = "This link is no longer valid - request a new one from the site."


def customer_by_token(token) -> Customer | None:
    """Resolve a purchases-page token, or None if it is unusable for any reason."""

    try:
        customer = Customer.objects.get(access_token=token)
    except (Customer.DoesNotExist, ValidationError, ValueError):
        return None

    return customer if customer.is_access_token_valid() else None


class PurchasesView(APIView):
    """Everything this customer has paid for, with the state of every download link."""

    def get(self, request, *args, **kwargs):
        customer = customer_by_token(kwargs.get("token"))
        if customer is None:
            return Response({"detail": PURCHASES_GONE}, status=status.HTTP_404_NOT_FOUND)

        orders = customer.orders.paid().prefetch_related("items").order_by("-paid_at", "-created_at")

        serializer = PurchaseOrderSerializer(orders, many=True, context={"request": request})
        return Response({"email": customer.email, "orders": serializer.data})


class RefreshOrderItemView(APIView):
    """New token for one file - what the "refresh link" button calls."""

    def post(self, request, *args, **kwargs):
        customer = customer_by_token(kwargs.get("token"))
        if customer is None:
            return Response({"detail": PURCHASES_GONE}, status=status.HTTP_404_NOT_FOUND)

        # Scoped to the customer, so a valid token cannot be used to refresh somebody else's file.
        items = OrderItem.objects.downloadable().of_customer(customer).filter(pk=kwargs.get("item_id"))
        refreshed = items.reissue_tokens()
        if not refreshed:
            return Response({"detail": "No such file in your purchases"}, status=status.HTTP_404_NOT_FOUND)

        serializer = PurchaseItemSerializer(refreshed[0], context={"request": request})
        return Response(serializer.data)


class RefreshAllOrderItemsView(APIView):
    """New tokens for every file of this customer, in one go."""

    def post(self, request, *args, **kwargs):
        customer = customer_by_token(kwargs.get("token"))
        if customer is None:
            return Response({"detail": PURCHASES_GONE}, status=status.HTTP_404_NOT_FOUND)

        refreshed = OrderItem.objects.downloadable().of_customer(customer).reissue_tokens()
        serializer = PurchaseItemSerializer(refreshed, many=True, context={"request": request})
        return Response(serializer.data)


class CartItemsView(APIView):
    """
    Products by id, for the cart that lives in the browser.

    The cart is localStorage (ADR-0010), so the server cannot render it from state it does not
    have - the page asks for the lines it holds. Unknown or deactivated ids are simply absent from
    the answer, which is how the cart drops what is no longer on sale, and a price that moved
    since the line was added arrives corrected.

    Deliberately the catalog's own card payload: a line added from the grid and a line refreshed
    here are then the same object, and both languages ride along like everywhere else in the API.
    """

    def get(self, request, *args, **kwargs):
        raw = request.query_params.get("ids", "")
        ids = [int(chunk) for chunk in raw.split(",") if chunk.strip().isdigit()][: settings.MAX_ORDER_ITEMS]

        products = Product.objects.active().for_listing().filter(pk__in=ids)

        return Response(ProductListSerializer(products, many=True, context={"request": request}).data)
