import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from manager_for_ynab.pending_income import ynab


_SEED_SQL = (Path(__file__).resolve().parents[2] / "testing" / "seed.sql").read_text()


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path) as con:
        con.executescript(_SEED_SQL)
    return path


@pytest.fixture
def ynab_configuration():
    with patch.object(ynab, "Configuration") as configuration:
        yield configuration


@pytest.fixture
def ynab_api_client():
    with patch.object(ynab, "ApiClient") as api_client:
        yield api_client


@pytest.fixture
def transactions_api():
    with patch.object(ynab, "TransactionsApi") as transactions_api_cls:
        yield transactions_api_cls.return_value
