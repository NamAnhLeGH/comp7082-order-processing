"""Run using synthetic data only. Not executed on import."""
import uuid

from repository import StoreRepository
from cart import ShoppingCart
from payments import FakePaymentGateway
from checkout import CheckoutService
from setup_db import initialize


def main():
    initialize()
    repo = StoreRepository()
    cart = ShoppingCart('demo-user', repo)
    cart.add_item('MOU-01', 2)
    cart.apply_discount('WELCOME10')
    # A new id per run: each run of the demo is a new checkout, not a repeat of the last one.
    request_id = f'demo-{uuid.uuid4().hex}'
    result = CheckoutService(repo, FakePaymentGateway()).checkout(cart, 'TEST_TOKEN', request_id)
    print('Order result:', result)


if __name__ == '__main__':
    main()
