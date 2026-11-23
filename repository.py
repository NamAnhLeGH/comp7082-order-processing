"""SQLite persistence for products, saved carts, inventory and orders."""
import sqlite3
from contextlib import contextmanager

from models import DuplicateRequestError, InsufficientStockError, Product, to_money


class StoreRepository:
    def __init__(self, db_path='shop.db'):
        self.db_path = db_path

    @contextmanager
    def _transaction(self):
        """One connection, one transaction: commit if the block finishes, roll back if it
        raises, and close the connection either way."""
        conn = sqlite3.connect(self.db_path, timeout=2)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get_product(self, sku):
        with self._transaction() as conn:
            row = conn.execute(
                'SELECT sku, name, price, stock FROM products WHERE sku = ?', (sku,)
            ).fetchone()
        if row is None:
            return None
        return Product(row[0], row[1], to_money(row[2]), row[3])

    def get_saved_cart(self, user_id):
        with self._transaction() as conn:
            return conn.execute(
                'SELECT sku, quantity FROM saved_cart WHERE user_id = ?', (user_id,)
            ).fetchall()

    def save_cart(self, user_id, lines):
        """Replace the user's saved cart. If any insert fails, the old cart stays."""
        with self._transaction() as conn:
            conn.execute('DELETE FROM saved_cart WHERE user_id = ?', (user_id,))
            conn.executemany(
                'INSERT INTO saved_cart (user_id, sku, quantity) VALUES (?, ?, ?)',
                [(user_id, line.sku, line.quantity) for line in lines],
            )

    def create_pending_order(self, user_id, lines, amount, request_id):
        """Reserve stock for every line and record the order as 'pending', all in one
        transaction. Returns the new order id.

        Raises InsufficientStockError or DuplicateRequestError; in both cases nothing
        is changed, including stock already taken for earlier lines.
        """
        with self._transaction() as conn:
            for line in lines:
                # The WHERE clause makes "check and subtract" one statement, so two buyers
                # cannot both take the last unit and stock cannot go below zero.
                cur = conn.execute(
                    'UPDATE products SET stock = stock - ? WHERE sku = ? AND stock >= ?',
                    (line.quantity, line.sku, line.quantity),
                )
                if cur.rowcount != 1:
                    raise InsufficientStockError(line.sku)
            try:
                cur = conn.execute(
                    'INSERT INTO orders (user_id, amount, status, request_id) VALUES (?, ?, ?, ?)',
                    (user_id, float(amount), 'pending', request_id),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicateRequestError(request_id) from exc
            return cur.lastrowid

    def finish_order(self, order_id, status, lines):
        """Store the payment outcome. Any outcome other than 'paid' gives the stock back."""
        with self._transaction() as conn:
            conn.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
            if status != 'paid':
                for line in lines:
                    conn.execute(
                        'UPDATE products SET stock = stock + ? WHERE sku = ?',
                        (line.quantity, line.sku),
                    )

    def get_order_by_request(self, request_id):
        """(id, user_id, amount, status) of the order made with this request id, or None."""
        with self._transaction() as conn:
            row = conn.execute(
                'SELECT id, user_id, amount, status FROM orders WHERE request_id = ?', (request_id,)
            ).fetchone()
        if row is None:
            return None
        return row[0], row[1], to_money(row[2]), row[3]

    def list_orders(self, user_id):
        """Only this user's orders, newest first."""
        with self._transaction() as conn:
            rows = conn.execute(
                'SELECT id, user_id, amount, status FROM orders WHERE user_id = ? ORDER BY id DESC',
                (user_id,),
            ).fetchall()
        return [(row[0], row[1], to_money(row[2]), row[3]) for row in rows]
