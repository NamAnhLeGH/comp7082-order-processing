# Order-processing system: reliable programming lab

COMP 7082, Security and Reliable Programming. Nam Anh Le, A01377048.

The starter application had intentional defects. This repository holds the corrected code, the
unit tests and the CI workflow.

- **[DEFECTS.md](DEFECTS.md)**: the 15 defects, what each one did, how it was fixed, the
  assumptions, and the test results.
- **Tests:** 56 test cases in `tests/`, run with one command.
- **CI:** `.github/workflows/tests.yml` runs the tests on every push and pull request.

## Running locally

Python 3.10 or newer.

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python setup_db.py
python demo.py
```

## Files

| File | What it holds |
|---|---|
| `models.py` | `Product`, `CartLine`, `OrderResult`, the `to_money` helper and the two error classes |
| `cart.py` | Shopping cart, quantity validation and discount rules |
| `repository.py` | SQLite access: products, saved carts, stock reservation and orders |
| `checkout.py` | Checkout workflow: reserve stock, charge, record the result |
| `payments.py` | Simulated payment gateway (unchanged from the starter) |
| `setup_db.py`, `demo.py` | Demo database and a sample run |
| `tests/` | `test_cart.py`, `test_repository.py`, `test_checkout.py`, the supplied `test_smoke.py`, and fixtures in `conftest.py` |

## How checkout works now

1. `request_id` and the payment token must be present.
2. If an order with this `request_id` already exists, that order is returned. Nothing is charged.
3. An empty cart returns `empty`.
4. In one database transaction, stock is taken for every line and a `pending` order is saved. If any
   product is short, nothing is taken and the result is `out_of_stock`.
5. The payment gateway is charged.
6. The order becomes `paid`, `declined` or `payment_error`. Unless it is `paid`, the stock is given back.
7. Only a paid order empties the cart.

## AI use

Claude Code (Anthropic) was used to help identify the defects and to draft the fixes, the tests and
this documentation.
