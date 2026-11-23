"""Shared fixtures. Every test gets its own temporary SQLite file, so tests never share data.

Seeded products (from setup_db.initialize):
    LAP-01  Laptop          999.99   stock 5
    MOU-01  Wireless mouse   29.95   stock 20
    USB-01  USB cable         9.99   stock 50
"""
import sqlite3

import pytest

from cart import ShoppingCart
from repository import StoreRepository
from setup_db import initialize


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / 'shop.db')
    initialize(path)
    return path


@pytest.fixture
def repo(db_path):
    return StoreRepository(db_path)


@pytest.fixture
def cart(repo):
    return ShoppingCart('alice', repo)


@pytest.fixture
def run_sql(db_path):
    """run_sql('UPDATE ...', params) changes the test database directly, the way another
    shopper or an admin would behind the cart's back. Returns the rows of a SELECT."""

    def _run(sql, params=()):
        conn = sqlite3.connect(db_path)
        try:
            with conn:
                return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    return _run
