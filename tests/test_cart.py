"""Unit tests for ShoppingCart: quantities, totals, discounts, save and load."""
from decimal import Decimal

import pytest

from cart import ShoppingCart


# --- quantities -------------------------------------------------------------------------


@pytest.mark.parametrize('bad', [0, -1, 1.5, '2', None, True])
def test_add_item_rejects_invalid_quantity(cart, bad):
    with pytest.raises(ValueError):
        cart.add_item('USB-01', bad)
    assert cart.lines == []


def test_add_item_unknown_product_returns_false(cart):
    assert cart.add_item('NOPE-99', 1) is False
    assert cart.lines == []


def test_adding_the_same_product_twice_merges_into_one_line(cart):
    assert cart.add_item('USB-01', 2)
    assert cart.add_item('USB-01', 3)

    assert len(cart.lines) == 1
    assert cart.lines[0].quantity == 5


def test_repeated_adds_cannot_exceed_stock(cart):
    # LAP-01 has 5 in stock. 3 + 3 = 6 must be refused even though each call asks for 3.
    assert cart.add_item('LAP-01', 3) is True
    assert cart.add_item('LAP-01', 3) is False
    assert cart.lines[0].quantity == 3


def test_add_item_allows_exactly_the_stock(cart):
    assert cart.add_item('LAP-01', 5) is True
    assert cart.add_item('LAP-01', 1) is False


def test_remove_item_partial_then_all(cart):
    cart.add_item('USB-01', 5)

    assert cart.remove_item('USB-01', 2) is True
    assert cart.lines[0].quantity == 3
    assert cart.remove_item('USB-01') is True
    assert cart.lines == []
    assert cart.remove_item('USB-01') is False


@pytest.mark.parametrize('bad', [0, -2, 1.5])
def test_remove_item_rejects_invalid_quantity(cart, bad):
    cart.add_item('USB-01', 5)

    with pytest.raises(ValueError):
        cart.remove_item('USB-01', bad)
    # A negative quantity used to make the line bigger. It must stay at 5.
    assert cart.lines[0].quantity == 5


# --- totals and discounts ---------------------------------------------------------------


def test_subtotal_is_exact_to_the_cent(cart):
    cart.add_item('LAP-01', 3)  # 3 x 999.99. As floats this is 2999.9700000000003

    assert cart.subtotal() == Decimal('2999.97')
    assert isinstance(cart.subtotal(), Decimal)


@pytest.mark.parametrize(
    'code, expected',
    [
        ('WELCOME10', '90.00'),  # 10% off 100.00
        ('STUDENT20', '80.00'),  # 20% off
        ('SAVE15', '85.00'),  # 15.00 off
        ('FREESHIP', '100.00'),  # valid code, no price change
    ],
)
def test_each_discount_code(cart, run_sql, code, expected):
    run_sql("INSERT INTO products VALUES ('BOX-01', 'Gift box', 100.00, 10)")
    cart.add_item('BOX-01', 1)

    assert cart.apply_discount(code) is True
    assert cart.total() == Decimal(expected)


def test_invalid_coupon_is_refused_and_changes_nothing(cart):
    cart.add_item('USB-01', 1)

    assert cart.apply_discount('FREE100') is False
    assert cart.apply_discount(None) is False
    assert cart.discount_code is None
    assert cart.total() == Decimal('9.99')


def test_discount_does_not_stack(cart, run_sql):
    run_sql("INSERT INTO products VALUES ('BOX-01', 'Gift box', 100.00, 10)")
    cart.add_item('BOX-01', 1)

    cart.apply_discount('WELCOME10')
    cart.apply_discount('WELCOME10')  # used to give 81.00
    assert cart.total() == Decimal('90.00')

    cart.apply_discount('STUDENT20')  # replaces WELCOME10; used to give 72.00 or less
    assert cart.total() == Decimal('80.00')


def test_total_follows_cart_edits_made_after_a_discount(cart, run_sql):
    run_sql("INSERT INTO products VALUES ('BOX-01', 'Gift box', 100.00, 10)")
    cart.add_item('BOX-01', 1)
    cart.apply_discount('WELCOME10')
    assert cart.total() == Decimal('90.00')

    cart.add_item('BOX-01', 1)  # the old code kept charging 90.00 for two boxes
    assert cart.total() == Decimal('180.00')

    cart.remove_item('BOX-01', 1)
    assert cart.total() == Decimal('90.00')


@pytest.mark.parametrize(
    'price, expected',
    [
        ('9.99', '0.00'),  # below the coupon: free, not -5.01
        ('15.00', '0.00'),  # exactly the coupon
        ('15.01', '0.01'),  # just above
    ],
)
def test_fixed_discount_never_makes_the_total_negative(cart, run_sql, price, expected):
    run_sql("INSERT INTO products VALUES ('EDGE-01', 'Edge case', ?, 10)", (float(price),))
    cart.add_item('EDGE-01', 1)
    cart.apply_discount('SAVE15')

    assert cart.total() == Decimal(expected)


def test_percent_discount_is_rounded_to_the_cent(cart):
    cart.add_item('MOU-01', 1)  # 29.95; 10% is 2.995, rounded half up to 3.00
    cart.apply_discount('WELCOME10')

    assert cart.discount_amount() == Decimal('3.00')
    assert cart.total() == Decimal('26.95')


# --- saved carts ------------------------------------------------------------------------


def test_save_then_load_restores_the_cart(cart, repo):
    cart.add_item('USB-01', 2)
    cart.add_item('MOU-01', 1)
    cart.save()

    fresh = ShoppingCart('alice', repo)
    assert fresh.load() == []
    assert {(line.sku, line.quantity) for line in fresh.lines} == {('USB-01', 2), ('MOU-01', 1)}


def test_loading_twice_does_not_double_the_cart(cart):
    cart.add_item('USB-01', 2)
    cart.save()

    cart.load()
    cart.load()

    assert len(cart.lines) == 1
    assert cart.lines[0].quantity == 2  # used to become 6: 2 in memory + 2 + 2


def test_load_reports_items_that_are_no_longer_available(cart, repo, run_sql):
    cart.add_item('USB-01', 2)
    cart.add_item('LAP-01', 4)
    cart.save()
    run_sql("UPDATE products SET stock = 1 WHERE sku = 'LAP-01'")  # someone else bought them

    fresh = ShoppingCart('alice', repo)
    skipped = fresh.load()

    assert skipped == ['LAP-01']
    assert [(line.sku, line.quantity) for line in fresh.lines] == [('USB-01', 2)]


def test_saved_carts_are_separate_per_user(cart, repo):
    cart.add_item('USB-01', 2)
    cart.save()

    other = ShoppingCart('bob', repo)
    other.load()

    assert other.lines == []
