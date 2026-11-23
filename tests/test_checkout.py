"""Unit tests for CheckoutService. The payment gateway is always a fake: the supplied
FakePaymentGateway for approve and decline, and small stand-ins for a gateway that breaks."""
import logging
from decimal import Decimal

import pytest

from checkout import CheckoutService
from cart import ShoppingCart
from payments import FakePaymentGateway

TOKEN = 'tok_SECRET_4242'


class BrokenGateway:
    """A gateway whose network call fails."""

    def __init__(self):
        self.calls = 0

    def charge(self, amount, payment_token):
        self.calls += 1
        raise ConnectionError('gateway timed out')


class MalformedGateway:
    """A gateway that answers, but not in the agreed shape."""

    def charge(self, amount, payment_token):
        return {'status': 'ok'}


def _stock(repo, sku):
    return repo.get_product(sku).stock


def test_empty_cart_is_not_charged(cart, repo):
    gateway = FakePaymentGateway()

    result = CheckoutService(repo, gateway).checkout(cart, TOKEN, 'r-1')

    assert (result.order_id, result.status, result.total) == (None, 'empty', Decimal('0.00'))
    assert gateway.calls == []
    assert repo.list_orders('alice') == []


def test_paid_checkout_charges_the_discounted_total_once(cart, repo):
    cart.add_item('MOU-01', 2)  # 59.90
    cart.apply_discount('WELCOME10')  # 5.99 off
    cart.save()
    gateway = FakePaymentGateway()

    result = CheckoutService(repo, gateway).checkout(cart, TOKEN, 'r-1')

    assert result.status == 'paid'
    assert result.total == Decimal('53.91')
    assert gateway.calls == [(Decimal('53.91'), TOKEN)]
    assert _stock(repo, 'MOU-01') == 18
    assert repo.list_orders('alice') == [(result.order_id, 'alice', Decimal('53.91'), 'paid')]
    # The cart is emptied in memory and in the saved copy.
    assert cart.lines == []
    assert cart.discount_code is None
    assert repo.get_saved_cart('alice') == []


def test_declined_payment_restores_stock_and_keeps_the_cart(cart, repo):
    cart.add_item('LAP-01', 2)
    gateway = FakePaymentGateway(should_approve=False)

    result = CheckoutService(repo, gateway).checkout(cart, TOKEN, 'r-1')

    assert result.status == 'declined'
    assert _stock(repo, 'LAP-01') == 5  # used to stay at 3: stock lost with no sale
    assert [(line.sku, line.quantity) for line in cart.lines] == [('LAP-01', 2)]
    assert repo.list_orders('alice')[0][3] == 'declined'


def test_gateway_exception_is_recorded_and_stock_restored(cart, repo, caplog):
    cart.add_item('USB-01', 4)
    gateway = BrokenGateway()

    with caplog.at_level(logging.ERROR):
        result = CheckoutService(repo, gateway).checkout(cart, TOKEN, 'r-1')

    assert result.status == 'payment_error'
    assert gateway.calls == 1
    assert _stock(repo, 'USB-01') == 50
    assert len(cart.lines) == 1
    # The failure is logged with its cause, not swallowed.
    assert 'gateway timed out' in caplog.text


def test_malformed_gateway_response_is_a_payment_error(cart, repo):
    cart.add_item('USB-01', 1)

    result = CheckoutService(repo, MalformedGateway()).checkout(cart, TOKEN, 'r-1')

    assert result.status == 'payment_error'
    assert _stock(repo, 'USB-01') == 50


def test_stock_sold_to_someone_else_stops_checkout_before_payment(cart, repo, run_sql):
    cart.add_item('USB-01', 2)
    cart.add_item('LAP-01', 3)
    run_sql("UPDATE products SET stock = 1 WHERE sku = 'LAP-01'")  # sold while we shopped
    gateway = FakePaymentGateway()

    result = CheckoutService(repo, gateway).checkout(cart, TOKEN, 'r-1')

    assert (result.order_id, result.status) == (None, 'out_of_stock')
    assert gateway.calls == []  # the customer is not charged for goods we do not have
    assert _stock(repo, 'LAP-01') == 1  # used to go to -2
    assert _stock(repo, 'USB-01') == 50  # the first line was not taken either
    assert len(cart.lines) == 2


def test_repeated_request_returns_the_first_order_without_charging_again(cart, repo):
    cart.add_item('USB-01', 3)
    gateway = FakePaymentGateway()
    service = CheckoutService(repo, gateway)

    first = service.checkout(cart, TOKEN, 'r-1')
    second = service.checkout(cart, TOKEN, 'r-1')  # double click or network retry

    assert second == first
    assert second.status == 'paid'
    assert len(gateway.calls) == 1
    assert _stock(repo, 'USB-01') == 47
    assert len(repo.list_orders('alice')) == 1


def test_repeated_request_with_a_refilled_cart_still_does_not_charge_twice(cart, repo):
    gateway = FakePaymentGateway()
    service = CheckoutService(repo, gateway)
    cart.add_item('USB-01', 1)
    first = service.checkout(cart, TOKEN, 'r-1')

    cart.add_item('LAP-01', 1)
    second = service.checkout(cart, TOKEN, 'r-1')

    assert second == first
    assert len(gateway.calls) == 1
    assert _stock(repo, 'LAP-01') == 5


def test_request_id_of_another_user_is_refused(cart, repo):
    service = CheckoutService(repo, FakePaymentGateway())
    cart.add_item('USB-01', 1)
    service.checkout(cart, TOKEN, 'r-1')

    bob = ShoppingCart('bob', repo)
    bob.add_item('USB-01', 1)

    with pytest.raises(ValueError):
        service.checkout(bob, TOKEN, 'r-1')
    assert repo.list_orders('bob') == []


@pytest.mark.parametrize('token, request_id', [(TOKEN, None), (TOKEN, ''), (None, 'r-1'), ('', 'r-1')])
def test_request_id_and_token_are_required(cart, repo, token, request_id):
    cart.add_item('USB-01', 1)
    gateway = FakePaymentGateway()

    with pytest.raises(ValueError):
        CheckoutService(repo, gateway).checkout(cart, token, request_id)

    assert gateway.calls == []
    assert _stock(repo, 'USB-01') == 50


def test_payment_token_is_never_printed_or_logged(cart, repo, capsys, caplog):
    cart.add_item('USB-01', 1)

    with caplog.at_level(logging.DEBUG):
        CheckoutService(repo, FakePaymentGateway()).checkout(cart, TOKEN, 'r-1')
        cart.add_item('USB-01', 1)
        CheckoutService(repo, BrokenGateway()).checkout(cart, TOKEN, 'r-2')

    printed = capsys.readouterr()
    assert TOKEN not in printed.out + printed.err
    assert TOKEN not in caplog.text


def test_order_fully_covered_by_a_coupon_skips_the_gateway(cart, repo):
    cart.add_item('USB-01', 1)  # 9.99, less than the 15.00 coupon
    cart.apply_discount('SAVE15')
    gateway = FakePaymentGateway(should_approve=False)  # would decline if it were asked

    result = CheckoutService(repo, gateway).checkout(cart, TOKEN, 'r-1')

    assert (result.status, result.total) == ('paid', Decimal('0.00'))
    assert gateway.calls == []
    assert _stock(repo, 'USB-01') == 49
