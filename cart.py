"""Shopping cart and discount rules."""
import logging
from decimal import Decimal

from models import CartLine, to_money

logger = logging.getLogger(__name__)

# code -> (kind, value). A cart holds one code at a time, and the discount is always
# worked out from the current subtotal.
DISCOUNTS = {
    'WELCOME10': ('percent', Decimal('10')),
    'STUDENT20': ('percent', Decimal('20')),
    'SAVE15': ('fixed', Decimal('15.00')),
    # Valid code, but this model has no shipping charge, so the price does not change.
    'FREESHIP': ('shipping', Decimal('0')),
}


def _check_quantity(quantity):
    # bool is a subclass of int, so without the first test True would count as 1.
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        raise ValueError(f'quantity must be a positive whole number, got {quantity!r}')


class ShoppingCart:
    def __init__(self, user_id, repository):
        self.user_id = user_id
        self.repository = repository
        self.lines = []
        self.discount_code = None

    def add_item(self, sku, quantity):
        """Add a product. Returns False for an unknown product or not enough stock."""
        _check_quantity(quantity)
        product = self.repository.get_product(sku)
        if not product:
            logger.info('Unknown product %r', sku)
            return False
        existing = next((x for x in self.lines if x.sku == sku), None)
        # Compare stock with everything the cart would hold, not only this call's quantity.
        wanted = quantity + (existing.quantity if existing else 0)
        if product.stock < wanted:
            logger.info('Not enough stock for %s: wanted %d, have %d', sku, wanted, product.stock)
            return False
        if existing:
            existing.quantity = wanted
        else:
            self.lines.append(CartLine(sku, product.name, product.price, quantity))
        return True

    def remove_item(self, sku, quantity=None):
        """Remove some of a product, or all of it when no quantity is given."""
        if quantity is not None:
            _check_quantity(quantity)
        for line in self.lines:
            if line.sku == sku:
                if quantity is None or quantity >= line.quantity:
                    self.lines.remove(line)
                else:
                    line.quantity -= quantity
                return True
        logger.info('Item %r is not in the cart', sku)
        return False

    def subtotal(self):
        return to_money(sum((line.unit_price * line.quantity for line in self.lines), Decimal('0')))

    def discount_amount(self):
        """Dollars taken off by the current code. Never more than the subtotal."""
        if self.discount_code is None:
            return Decimal('0.00')
        kind, value = DISCOUNTS[self.discount_code]
        subtotal = self.subtotal()
        if kind == 'percent':
            amount = subtotal * value / 100
        elif kind == 'fixed':
            amount = value
        else:
            amount = Decimal('0')
        return min(to_money(amount), subtotal)

    def total(self):
        # Computed on every call, so it always matches the lines that are in the cart now.
        return self.subtotal() - self.discount_amount()

    def apply_discount(self, code):
        """Set the cart's discount code. A new code replaces the old one; codes do not stack."""
        if not isinstance(code, str) or code not in DISCOUNTS:
            logger.info('Invalid coupon %r', code)
            return False
        self.discount_code = code
        return True

    def clear(self):
        self.lines.clear()
        self.discount_code = None

    def load(self):
        """Replace the cart's lines with the saved cart.

        Returns the SKUs that could not be restored (product gone, stock too low, or a bad
        saved quantity), so the caller can tell the user.
        """
        self.lines.clear()
        skipped = []
        for sku, quantity in self.repository.get_saved_cart(self.user_id):
            try:
                restored = self.add_item(sku, quantity)
            except ValueError:
                restored = False
            if not restored:
                skipped.append(sku)
        return skipped

    def save(self):
        self.repository.save_cart(self.user_id, self.lines)
