from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from sales.models import Order, OrderItem, PaymentCallbackLog, Transaction


class ReadOnlyAdmin(admin.ModelAdmin):
    """Sales data is written by the checkout and the payment callback, never by hand."""

    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DownloadColumnsMixin:
    """The state of a line's download link - shown both inline and standalone."""

    @admin.display(boolean=True, description="Link live")
    def is_downloadable(self, obj: OrderItem):
        return obj.is_token_valid()

    @admin.display(description="Download link")
    def download_link(self, obj: OrderItem):
        """
        The customer's own link, relative.

        Relative rather than absolute so it needs no request: the previous version stashed one on
        the ModelAdmin, which is a single instance shared by every thread of the process. The admin
        is served from the same origin as the API, so the href resolves either way, and following
        it does not move `download_count` - see DownloadFileView.
        """

        if obj.token is None:
            return "-"

        return format_html("<a href='{url}'>{text}</a>", url=reverse("download-file", args=[obj.token]), text=obj.token)


class OrderItemInline(DownloadColumnsMixin, admin.TabularInline):
    model = OrderItem
    fields = ["product", "product_name", "unit_price", "is_downloadable", "download_count", "download_link"]
    readonly_fields = fields
    extra = 0
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class TransactionInline(admin.TabularInline):
    """An order can have several invoices - a currency switch mints a new one (docs/architecture.md)."""

    model = Transaction
    fields = ["txn_id", "status", "amount", "currency", "source_amount", "commission", "created_at"]
    readonly_fields = fields
    extra = 0
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ReadOnlyAdmin):
    list_display = ("id", "customer", "status", "total_price", "created_at", "paid_at")
    list_filter = ("status", "created_at", "paid_at")
    search_fields = ("customer__email", "id")
    list_select_related = ("customer",)
    readonly_fields = ("customer", "status", "total_price", "invoice_url", "created_at", "updated_at", "paid_at")
    inlines = [OrderItemInline, TransactionInline]


@admin.register(OrderItem)
class OrderItemAdmin(DownloadColumnsMixin, ReadOnlyAdmin):
    list_display = ("order", "product_name", "unit_price", "is_downloadable", "download_count", "order_status")
    list_filter = ("order__status", "product__country", "product__document_type")
    search_fields = ("order__customer__email", "product_name", "token")
    list_select_related = ("order", "order__customer", "product")
    fields = (
        "order",
        "product",
        "product_name",
        "unit_price",
        "token_expires_at",
        "download_link",
        "download_count",
        "first_downloaded_at",
        "last_downloaded_at",
    )
    readonly_fields = fields
    exclude = ("token",)

    @admin.display(description="Order status")
    def order_status(self, obj: OrderItem):
        return obj.order.get_status_display()


@admin.register(Transaction)
class TransactionAdmin(ReadOnlyAdmin):
    fields = (
        "order",
        "status",
        "txn_id",
        "amount",
        "currency",
        "pending_amount",
        "tx_urls",
        "source_amount",
        "source_currency",
        "source_rate",
        "commission",
        "confirmations",
        "created_at",
        "updated_at",
        "comment",
        "merchant",
        "merchant_id",
    )
    readonly_fields = fields
    list_display = ("id", "order", "amount", "currency", "status", "pending_amount", "commission", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__customer__email", "txn_id")
    list_select_related = ("order", "order__customer")


@admin.register(PaymentCallbackLog)
class PaymentCallbackLogAdmin(ReadOnlyAdmin):
    list_display = ("id", "received_at", "txn_id", "order", "callback_status")
    list_filter = ("received_at",)
    search_fields = ("txn_id", "order__id", "order__customer__email")
    list_select_related = ("order",)
    readonly_fields = ("order", "txn_id", "payload", "received_at")

    @admin.display(description="Status")
    def callback_status(self, obj: PaymentCallbackLog):
        return obj.payload.get("status", "-") if isinstance(obj.payload, dict) else "-"
