"""Checkout workflow: reserve stock, charge, then record the outcome."""
import logging
from decimal import Decimal

from models import DuplicateRequestError, InsufficientStockError, OrderResult

logger = logging.getLogger(__name__)


class CheckoutService:
    def __init__(self, repository, payment_gateway):
        self.repository = repository
        self.payment_gateway = payment_gateway

    def checkout(self, cart, payment_token, request_id):
        """Turn the cart into an order.

        request_id identifies one checkout attempt. Sending the same id again returns the
        first order instead of charging a second time.

        Statuses: 'paid', 'declined', 'payment_error', 'out_of_stock', 'empty'.
        Only 'paid' empties the cart and keeps the stock.
        """
        if not request_id:
            raise ValueError('request_id is required')
        if not payment_token:
            raise ValueError('payment_token is required')

        # Checked before the empty-cart test: after a paid order the cart is empty, and a
        # repeated request must still get the original order back.
        earlier = self._earlier_order(cart, request_id)
        if earlier is not None:
            return earlier

        if not cart.lines:
            return OrderResult(None, 'empty', Decimal('0.00'))

        amount = cart.total()
        try:
            order_id = self.repository.create_pending_order(
                cart.user_id, cart.lines, amount, request_id
            )
        except InsufficientStockError as exc:
            logger.info('Checkout %s stopped: %s', request_id, exc)
            return OrderResult(None, 'out_of_stock', amount)
        except DuplicateRequestError:
            # Another request with the same id got in between our lookup and our insert.
            return self._earlier_order(cart, request_id)

        status = self._charge(amount, payment_token, request_id)
        self.repository.finish_order(order_id, status, cart.lines)
        if status == 'paid':
            cart.clear()
            cart.save()
        return OrderResult(order_id, status, amount)

    def _earlier_order(self, cart, request_id):
        row = self.repository.get_order_by_request(request_id)
        if row is None:
            return None
        order_id, user_id, amount, status = row
        if user_id != cart.user_id:
            # Never hand one user's order to another user who sends the same id.
            raise ValueError('request_id was already used')
        return OrderResult(order_id, status, amount)

    def _charge(self, amount, payment_token, request_id):
        """'paid', 'declined' or 'payment_error'. The token is never logged."""
        if amount == 0:
            return 'paid'  # a discount covered everything; there is nothing to charge
        try:
            response = self.payment_gateway.charge(amount, payment_token)
            approved = response['approved']
        except Exception:
            # The gateway is outside our control and can fail in any way. Record what
            # happened (without the token) instead of hiding it.
            logger.exception('Payment gateway failed for request %s', request_id)
            return 'payment_error'
        return 'paid' if approved is True else 'declined'
