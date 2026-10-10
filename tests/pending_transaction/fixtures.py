from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from testing.fixtures import execute_seed
from testing.fixtures import seed_paths

_SEED_TRANSACTIONS_SQL = Path(__file__).with_name("seed-transactions.sql")


@pytest.fixture()
def db(request, tmp_path):
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path) as con:
        execute_seed(con, *seed_paths(request, _SEED_TRANSACTIONS_SQL))
    return path


@pytest.fixture
def ynab_configuration():
    with patch("manager_for_ynab.pending_transaction.Configuration") as configuration:
        yield configuration


@pytest.fixture
def ynab_api_client():
    with patch("manager_for_ynab.pending_transaction.ApiClient") as api_client:
        api_client.return_value = AsyncMock()
        yield api_client


@pytest.fixture
def transactions_api():
    with patch(
        "manager_for_ynab.pending_transaction.TransactionsApi"
    ) as transactions_api_cls:
        transactions_api_cls.return_value = AsyncMock()
        yield transactions_api_cls.return_value
