from django.urls import path

from .views import (
    CartItemsView,
    DownloadFileView,
    OrderCreateView,
    PlisioCallbackView,
    PurchasesView,
    RefreshAllOrderItemsView,
    RefreshOrderItemView,
    SendDownloadLinksView,
)

urlpatterns = [
    path("cart/items/", CartItemsView.as_view(), name="cart-items"),
    path("order/", OrderCreateView.as_view(), name="order-create"),
    # No trailing slash: this is the URL registered with Plisio, and it is not ours to change.
    path("order/status", PlisioCallbackView.as_view(), name="plisio-callback"),
    path("send-links/", SendDownloadLinksView.as_view(), name="send-links"),
    path("files/<uuid:uuid>/", DownloadFileView.as_view(), name="download-file"),
    # Purchases page. The token in the path is the whole authentication, see ADR-0002.
    path("purchases/<uuid:token>/", PurchasesView.as_view(), name="purchases"),
    path(
        "purchases/<uuid:token>/refresh/<int:item_id>/",
        RefreshOrderItemView.as_view(),
        name="purchases-refresh",
    ),
    path(
        "purchases/<uuid:token>/refresh-all/",
        RefreshAllOrderItemsView.as_view(),
        name="purchases-refresh-all",
    ),
]
