from django.conf import settings
from django.db.transaction import atomic
from rest_framework import serializers

from catalog.models import Product
from customer.models import Customer
from customer.validators import validate_email_domain
from sales.models import Order, OrderItem


class OrderSerializer(serializers.ModelSerializer):
    """
    Order serializer for making an order.

    Accepts an e-mail, a list of product ids and the site language; the price is computed here,
    never taken from the client. There is no quantity - a template is bought once (ADR-0001).
    """

    email = serializers.EmailField(write_only=True, validators=[validate_email_domain])
    language = serializers.ChoiceField(choices=settings.LANGUAGES, write_only=True, required=False)
    products = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.active(),
        many=True,
        allow_empty=False,
        write_only=True,
    )
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Order
        fields = ["email", "language", "products", "total_price"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Set by validate() when the customer already has a live invoice for this cart.
        self.reused_order: Order | None = None

    def validate_products(self, products: list[Product]) -> list[Product]:
        if len(products) > settings.MAX_ORDER_ITEMS:
            raise serializers.ValidationError(f"At most {settings.MAX_ORDER_ITEMS} products per order")

        ids = [product.pk for product in products]
        if len(set(ids)) != len(ids):
            # The same file twice is not a bigger purchase, it is a mistake - and the unique
            # constraint on (order, product) would refuse it anyway, with an uglier error.
            raise serializers.ValidationError("Each product may appear only once in an order")

        return products

    def validate(self, data):
        data["total_price"] = sum(product.price for product in data["products"])
        self.reused_order = Order.objects.reusable(data["email"], data["products"])

        return data

    @atomic
    def create(self, validated_data):
        language = validated_data.pop("language", None)

        if self.reused_order is not None:
            # Still worth recording: they may have switched the site language since the invoice.
            self.reused_order.customer.set_language(language)
            return self.reused_order

        products = validated_data.pop("products")
        total_price = validated_data.pop("total_price")
        customer, _ = Customer.objects.get_or_create(email=validated_data.pop("email"))
        customer.set_language(language)

        order = Order.objects.create(customer=customer, total_price=total_price, **validated_data)

        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    product=product,
                    # Snapshot: the catalog is free to change afterwards, this order is not.
                    product_name=product.name,
                    unit_price=product.price,
                )
                for product in products
            ]
        )

        return order


class SendDownloadLinksSerializer(serializers.Serializer):
    """
    Serializer for sending download links.

    Accepts the email and, optionally, the site language to answer in.
    """

    email = serializers.EmailField()
    language = serializers.ChoiceField(choices=settings.LANGUAGES, required=False)


class PurchaseItemSerializer(serializers.ModelSerializer):
    """A bought file: named and priced as of the day it was bought, plus the state of its link."""

    is_downloadable = serializers.BooleanField(source="is_token_valid", read_only=True)
    download_url = serializers.SerializerMethodField()
    expires_at = serializers.DateTimeField(source="token_expires_at", read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product_name", "unit_price", "is_downloadable", "download_url", "expires_at"]

    def get_download_url(self, obj: OrderItem) -> str | None:
        # No link at all rather than a dead one: an expired token has to be refreshed first.
        if not obj.is_token_valid():
            return None

        return obj.get_download_url(self.context.get("request"))


class PurchaseOrderSerializer(serializers.ModelSerializer):
    """One paid order with everything the customer can download from it."""

    items = PurchaseItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "status", "total_price", "created_at", "paid_at", "items"]


class CartItemSerializer(serializers.ModelSerializer):
    """
    What the cart needs to draw a line: the cart itself lives in the browser, so the storefront
    asks for these by id (see ADR-0009).
    """

    preview_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "name", "price", "preview_url"]

    def get_preview_url(self, obj: Product) -> str | None:
        preview = obj.preview
        return preview.card.url if preview and preview.card else None
