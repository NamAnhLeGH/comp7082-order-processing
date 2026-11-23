"""Domain objects for the order-processing application."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal('0.01')


def to_money(value) -> Decimal:
    """Turn a number into an exact amount of dollars and cents.

    Going through str() keeps 29.95 as 29.95. Decimal(29.95) would copy the float's
    binary error (29.949999999999999289...) into the result.
    """
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


class InsufficientStockError(Exception):
    """A product does not have enough stock left for the quantity asked for."""

    def __init__(self, sku):
        super().__init__(f'Not enough stock for {sku}')
        self.sku = sku


class DuplicateRequestError(Exception):
    """An order with this request id already exists."""


@dataclass
class Product:
    sku: str
    name: str
    price: Decimal
    stock: int


@dataclass
class CartLine:
    sku: str
    name: str
    unit_price: Decimal
    quantity: int


@dataclass
class OrderResult:
    order_id: int | None
    status: str
    total: Decimal
