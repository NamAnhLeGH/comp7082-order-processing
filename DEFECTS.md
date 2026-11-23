# Defects found and fixed

COMP 7082, Security and Reliable Programming lab. Nam Anh Le, A01377048.

The "Before" column is what the starter code actually did when I ran it. The "Test" column names
the test that now proves the fix. Tests marked (cart), (repo) and (checkout) are in
`tests/test_cart.py`, `tests/test_repository.py` and `tests/test_checkout.py`.

## Security defects

| # | Where | Before | Fix | Test |
|---|---|---|---|---|
| 1 | `repository.py`, `get_product` and `get_saved_cart` | **SQL injection.** The queries were built with f-strings. `get_product("x' OR '1'='1")` returned the Laptop row, and `get_saved_cart("nobody' OR '1'='1")` returned another user's cart. | Both queries use `?` parameters, so the input is always data and never SQL. | `test_get_product_treats_sql_in_the_sku_as_plain_text`, `test_get_saved_cart_cannot_read_other_users_carts` (repo) |
| 2 | `checkout.py`, `checkout` | **Payment token printed.** Every checkout wrote `Charging payment token: tok_SECRET_4242` to the console, where it ends up in logs. | The line is gone. Logging uses the request id only, never the token. | `test_payment_token_is_never_printed_or_logged` (checkout) |
| 3 | `repository.py`, `list_orders` | **Everyone's orders returned.** The `user_id` argument was ignored: `list_orders('alice')` also returned Bob's order. | Added `WHERE user_id = ?`. | `test_list_orders_returns_only_that_users_orders` (repo) |

## Checkout and inventory defects

| # | Where | Before | Fix | Test |
|---|---|---|---|---|
| 4 | `checkout.py`, `checkout` | **Failed payment still took the stock and the cart.** Stock was subtracted before charging and never returned. A declined payment for 2 laptops left stock at 3 instead of 5, and the customer's cart was emptied. | Stock is reserved together with a `pending` order. `finish_order` gives the stock back for any result except `paid`. The cart is cleared only when the order is paid. | `test_declined_payment_restores_stock_and_keeps_the_cart`, `test_gateway_exception_is_recorded_and_stock_restored` (checkout), `test_finish_order_gives_stock_back_unless_paid` (repo) |
| 5 | `checkout.py` and `repository.py`, `update_stock` | **Overselling.** Stock was checked only when an item was added to the cart. With 1 laptop left, a cart of 3 was charged and stock became -2. Each line was also its own transaction, so a failure half-way left some lines subtracted. | `create_pending_order` runs `UPDATE ... WHERE sku = ? AND stock >= ?` for every line inside one transaction. If any line is short, everything rolls back and checkout returns `out_of_stock` before the customer is charged. The table also has `CHECK (stock >= 0)`. | `test_stock_sold_to_someone_else_stops_checkout_before_payment` (checkout), `test_create_pending_order_is_all_or_nothing`, `test_stock_can_never_go_below_zero` (repo) |
| 6 | `checkout.py`, `checkout`; `setup_db.py` | **Duplicate transactions.** `request_id` was stored but never used. Sending the same request twice charged twice and created two orders. A missing `request_id` only printed a message, inside a branch that ran just for orders over 1000, and checkout carried on. | Checkout first looks for an order with that `request_id` and returns it without charging. `orders.request_id` has a unique index, so two requests at the same moment cannot both insert. `request_id` and the token are required (`ValueError`). A request id that belongs to another user is refused. | `test_repeated_request_returns_the_first_order_without_charging_again`, `test_repeated_request_with_a_refilled_cart_still_does_not_charge_twice`, `test_request_id_of_another_user_is_refused`, `test_request_id_and_token_are_required` (checkout), `test_same_request_id_cannot_create_two_orders` (repo) |
| 7 | `checkout.py`, `checkout` | **Payment errors hidden.** `except Exception:` set a status and threw the error away, so nobody could find out why a payment failed. A response without the `approved` key was treated the same way by accident. | The exception is logged with `logger.exception` (no token). Reading `response['approved']` is inside the `try`, and only `True` counts as approved. | `test_gateway_exception_is_recorded_and_stock_restored`, `test_malformed_gateway_response_is_a_payment_error` (checkout) |

## Cart and money defects

| # | Where | Before | Fix | Test |
|---|---|---|---|---|
| 8 | `cart.py`, `apply_discount` | **Discounts stacked.** Each call discounted the already discounted total. `WELCOME10` twice on 100.00 gave 81.00, and adding `STUDENT20` gave 64.80. | The cart stores one code. The discount is always calculated from the subtotal, and a new code replaces the old one. | `test_discount_does_not_stack` (cart) |
| 9 | `cart.py`, `total` | **Total not updated after editing the cart.** The discounted total was saved as a number. After a discount on one 100.00 box (90.00), adding a second box still showed 90.00, so the second box was free. | `discounted_total` is removed. `total()` is calculated from the current lines every time. | `test_total_follows_cart_edits_made_after_a_discount` (cart) |
| 10 | `cart.py`, `apply_discount` | **Negative total.** `SAVE15` on a 9.99 cart gave -5.01, which checkout then sent to the payment gateway. | The discount can never be more than the subtotal. An order whose total is 0.00 is recorded as paid without calling the gateway. | `test_fixed_discount_never_makes_the_total_negative` (cart), `test_order_fully_covered_by_a_coupon_skips_the_gateway` (checkout) |
| 11 | `cart.py`, `add_item` and `remove_item` | **No quantity validation.** `add_item('USB-01', -3)` was accepted and made the subtotal -29.97. Quantity 0 added an empty line. `remove_item('USB-01', -2)` raised the quantity from 5 to 7. | `_check_quantity` raises `ValueError` unless the quantity is a whole number above 0 (`True` and `1.5` are refused too). | `test_add_item_rejects_invalid_quantity`, `test_remove_item_rejects_invalid_quantity` (cart) |
| 12 | `cart.py`, `add_item` | **Stock check ignored the cart.** Only the new quantity was compared with stock. With 5 laptops, adding 3 and then 3 again put 6 in the cart. | The check uses the quantity already in the cart plus the new quantity. | `test_repeated_adds_cannot_exceed_stock`, `test_add_item_allows_exactly_the_stock` (cart) |
| 13 | `cart.py`, `load` | **Loading twice doubled the cart.** `load` added the saved lines on top of what was already there: save 2, load, load gave 6. Items that could not be restored disappeared with only a `print`. | `load` empties the lines first and returns the SKUs it could not restore. | `test_loading_twice_does_not_double_the_cart`, `test_load_reports_items_that_are_no_longer_available` (cart) |
| 14 | `models.py`, `cart.py` | **Money as floats.** 3 x 999.99 gave 2999.9700000000003. | Prices and totals are `Decimal`. `to_money` converts through `str()` and rounds to cents, half up. | `test_subtotal_is_exact_to_the_cent`, `test_percent_discount_is_rounded_to_the_cent` (cart), `test_get_product_returns_an_exact_decimal_price` (repo) |

## Resource handling defect

| # | Where | Before | Fix | Test |
|---|---|---|---|---|
| 15 | `repository.py`, every method; `setup_db.py`, `initialize` | **Connections leaked on errors.** `conn.close()` was a plain statement after the query, so any exception skipped it and left the connection (and its lock on the file) open. `initialize` used `with sqlite3.connect(...)`, which commits but does not close. | One helper, `_transaction()`, opens the connection, commits if the block finishes, rolls back if it raises, and always closes. `save_cart` therefore keeps the old cart when the new one cannot be written. | `test_failed_save_keeps_the_previous_saved_cart` (repo) |

Smaller changes made along the way: `print` calls in the cart and checkout became `logging` calls,
the schema gained `NOT NULL`, `CHECK` and a primary key on `saved_cart (user_id, sku)`, and
`demo.py` makes a new request id on every run (with defect 6 fixed, a fixed id would correctly
return the first run's order forever).

`payments.py` is unchanged. The supplied simulated gateway is still what checkout calls.

## Assumptions

The lab leaves these open, so this is what I decided:

1. **One coupon per cart.** The latest valid code replaces the earlier one. An invalid code is
   refused and the current code stays.
2. **Rounding.** A percentage discount is rounded to the cent, half up, and then subtracted
   (29.95 with 10% off is 29.95 - 3.00 = 26.95).
3. **`FREESHIP`** is a valid code that does not change the price, because this model has no
   shipping charge.
4. **Invalid input raises, business outcomes return a value.** A bad quantity or a missing request id
   is a caller mistake and raises `ValueError`. Unknown product, not enough stock and invalid coupon
   return `False`, as in the starter. Checkout reports `empty`, `out_of_stock`, `declined`,
   `payment_error` or `paid` in `OrderResult.status`.
5. **Same request id, same answer.** A repeated request returns the first order whatever its status.
   To try again after a declined payment the client sends a new request id.
6. **Declined or failed payment:** the order is kept with that status as a record, the stock goes
   back on sale and the customer keeps the cart. After `payment_error` we do not know if the
   gateway took the money, so the order row is there for someone to check.
7. **Prices in the cart** are the prices when the item was added. Stock is checked again at checkout.
8. **The coupon is not saved with a saved cart** (the table has no column for it). It is applied
   again after loading.
9. **Money stays `REAL` in SQLite**, as in the given schema, and is converted to `Decimal` and
   rounded to cents whenever it is read.

Known limit: if the program stops between reserving stock and recording the payment result, the
order stays `pending` and keeps its stock. A real system would release old pending orders with a
scheduled job. I left that out as beyond this lab.

An old `shop.db` made by the starter keeps its old tables (`CREATE TABLE IF NOT EXISTS` does not
change them). Delete it and run `python setup_db.py` again to get the new constraints.

## Test results

56 test cases from 41 test functions (2 supplied smoke tests, 18 cart, 9 repository, 12 checkout).
Every test uses its own temporary SQLite file through pytest's `tmp_path`.

```
$ python -m pytest -q
........................................................                 [100%]
56 passed in 1.67s
```

Run against the original starter code, 35 of the 45 cart and checkout test cases fail, and the
repository tests cannot run at all, which is how I know the tests check the fixes and not just
the happy path.

## GitHub Actions

Workflow: `.github/workflows/tests.yml`. It runs on every push and pull request, on Python 3.10
and 3.13, installs `requirements.txt` and runs `python -m pytest -q`.

Successful run: CI_RUN_LINK
