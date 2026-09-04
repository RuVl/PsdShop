"""
Plisio, in the words our models use.

The callback is the only thing that ever tells us about an invoice: Plisio's `operations` endpoint
answers with nine fields unless the account has White Label enabled - no amount, no rate, no
commission - so there is nothing to read back from it. What lives here is the translation of a
callback payload into a `Transaction`, and the one place an invoice status turns into an order
state change.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.transaction import atomic

from sales.models import Order, OrderItem

logger = logging.getLogger(__name__)

# Plisio invoice status -> our order status.
STATUS_MAP = {
    "new": Order.OrderStatus.PENDING,
    "pending": Order.OrderStatus.PENDING,
    "pending internal": Order.OrderStatus.PENDING,
    "completed": Order.OrderStatus.PAID,
    "expired": Order.OrderStatus.EXPIRED,
    "mismatch": Order.OrderStatus.OVERPAID,
    "error": Order.OrderStatus.ERROR,
    "cancelled": Order.OrderStatus.CANCELLED,
    "cancelled duplicate": Order.OrderStatus.PENDING,  # A customer has switched to another cryptocurrency
}


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def callback_to_fields(data: dict) -> dict[str, Any]:
    """
    A Plisio callback payload in the words `Transaction` uses, minus the order it belongs to.

    A key the payload does not carry is left out entirely, so a repeated callback cannot blank a
    column an earlier one filled - Plisio sends the same invoice several times and the later
    messages are not always the richer ones.

    Two names are worth knowing here. `invoice_commission` is what Plisio kept, quoted in the
    invoice's **cryptocurrency**, and `source_rate` is how much of that cryptocurrency one unit of
    the fiat currency buys - so fiat is crypto divided by the rate, never multiplied (see
    `statistics.money_totals`).
    """

    fields = {
        "status": data.get("status"),
        "amount": _decimal(data.get("amount")),
        "currency": data.get("currency"),
        "merchant": data.get("merchant"),
        "merchant_id": data.get("merchant_id"),
        "comment": data.get("comment"),
        "source_amount": _decimal(data.get("source_amount")),
        "source_currency": data.get("source_currency"),
        "source_rate": _decimal(data.get("source_rate")),
        "commission": _decimal(data.get("invoice_commission")),
        "pending_amount": _decimal(data.get("pending_amount")),
        "confirmations": _int(data.get("confirmations")),
        "tx_urls": data.get("tx_urls") or None,
    }

    return {field: value for field, value in fields.items() if value is not None}


@atomic
def apply_order_status(order: Order, plisio_status: str | None) -> tuple[bool, list[OrderItem]]:
    """
    Move the order to what Plisio says about its invoice, handing the files over if it is paid.

    Returns (this is the first payment, lines delivered) - the caller decides about the e-mail,
    because only the first payment may send one. An expired or cancelled invoice only moves the
    status: with unlimited copies there is nothing to give back (docs/architecture.md).
    """

    order.status = STATUS_MAP.get(plisio_status, Order.OrderStatus.ERROR)
    order.save(update_fields=["status", "updated_at"])

    first_payment, items = False, []
    if order.status in (Order.OrderStatus.PAID, Order.OrderStatus.OVERPAID):
        first_payment = order.mark_paid()
        items = order.deliver()

    return first_payment, items
