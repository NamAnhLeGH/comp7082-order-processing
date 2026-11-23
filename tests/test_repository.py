"""Unit tests for StoreRepository: safe queries, per-user data, all-or-nothing writes."""
import sqlite3
from decimal import Decimal

import pytest

from models import CartLine, DuplicateRequestError, InsufficientStockError


def _line(sku, quantity, price='1.00'):
    return CartLine(sku, sku, Decimal(price), quantity)


def _stock(repo, sku):
    return repo.get_product(sku).stock


def test_get_product_treats_sql_in_the_sku_as_plain_text(repo):
    # With the old f-string query this matched every row and returned the first product.
    assert repo.get_product("x' OR '1'='1") is None
    # And this one would have run as a second condition. The table must be untouched.
    assert repo.get_product("x'; DROP TABLE products; --") is None
    assert repo.get_product('USB-01').name == 'USB cable'


def test_get_saved_cart_cannot_read_other_users_carts(repo):
    repo.save_cart('alice', [_line('USB-01', 2)])

    assert repo.get_saved_cart("nobody' OR '1'='1") == []
    assert repo.get_saved_cart('alice') == [('USB-01', 2)]


def test_get_product_returns_an_exact_decimal_price(repo):
    price = repo.get_product('MOU-01').price

    assert price == Decimal('29.95')
    assert isinstance(price, Decimal)


def test_list_orders_returns_only_that_users_orders(repo):
    alice_order = repo.create_pending_order('alice', [_line('USB-01', 1)], Decimal('9.99'), 'r-1')
    repo.create_pending_order('bob', [_line('USB-01', 1)], Decimal('9.99'), 'r-2')

    orders = repo.list_orders('alice')

    assert [(o[0], o[1]) for o in orders] == [(alice_order, 'alice')]
    assert repo.list_orders('carol') == []


def test_create_pending_order_is_all_or_nothing(repo):
    lines = [_line('USB-01', 2), _line('LAP-01', 6)]  # only 5 laptops exist

    with pytest.raises(InsufficientStockError) as error:
        repo.create_pending_order('alice', lines, Decimal('1.00'), 'r-1')

    assert error.value.sku == 'LAP-01'
    assert _stock(repo, 'USB-01') == 50  # the cables taken first were given back
    assert _stock(repo, 'LAP-01') == 5
    assert repo.get_order_by_request('r-1') is None


def test_stock_can_never_go_below_zero(repo):
    repo.create_pending_order('alice', [_line('LAP-01', 5)], Decimal('1.00'), 'r-1')

    with pytest.raises(InsufficientStockError):
        repo.create_pending_order('bob', [_line('LAP-01', 1)], Decimal('1.00'), 'r-2')

    assert _stock(repo, 'LAP-01') == 0


def test_same_request_id_cannot_create_two_orders(repo):
    repo.create_pending_order('alice', [_line('USB-01', 1)], Decimal('9.99'), 'r-1')

    with pytest.raises(DuplicateRequestError):
        repo.create_pending_order('alice', [_line('USB-01', 1)], Decimal('9.99'), 'r-1')

    assert _stock(repo, 'USB-01') == 49  # taken once, not twice
    assert len(repo.list_orders('alice')) == 1


def test_finish_order_gives_stock_back_unless_paid(repo):
    lines = [_line('USB-01', 3)]
    declined = repo.create_pending_order('alice', lines, Decimal('29.97'), 'r-1')
    repo.finish_order(declined, 'declined', lines)
    assert _stock(repo, 'USB-01') == 50

    paid = repo.create_pending_order('alice', lines, Decimal('29.97'), 'r-2')
    repo.finish_order(paid, 'paid', lines)
    assert _stock(repo, 'USB-01') == 47
    assert repo.get_order_by_request('r-2') == (paid, 'alice', Decimal('29.97'), 'paid')


def test_failed_save_keeps_the_previous_saved_cart(repo):
    repo.save_cart('alice', [_line('USB-01', 2)])

    # Quantity 0 breaks the table's CHECK, after the DELETE has already run.
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_cart('alice', [_line('MOU-01', 1), _line('LAP-01', 0)])

    assert repo.get_saved_cart('alice') == [('USB-01', 2)]
