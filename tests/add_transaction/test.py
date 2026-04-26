import sqlite3
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
import ynab

from manager_for_ynab.add_transaction import add_txn
from manager_for_ynab.add_transaction import build_parser
from manager_for_ynab.add_transaction import decimal
from manager_for_ynab.add_transaction import edit_distance


def _create_add_transaction_db(path: Path) -> None:
    seed_path = Path(__file__).parents[2] / "testing" / "seed.sql"
    contents = seed_path.read_text()
    with sqlite3.connect(path) as con:
        con.executescript(contents)


def test_build_parser_uses_expected_prog():
    parser = build_parser()
    assert parser.prog == "manager-for-ynab add-transaction"


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        pytest.param("kitten", "sitting", 3, id="classic-example"),
        pytest.param("", "abc", 3, id="empty-left"),
        pytest.param("abc", "abc", 0, id="equal"),
    ],
)
def test_edit_distance(left, right, expected):
    assert edit_distance(left, right) == expected


def test_decimal_strips_commas():
    assert decimal("1,234.56") == Decimal("1234.56")


@patch("manager_for_ynab.add_transaction.ynab.CategoriesApi")
@patch("manager_for_ynab.add_transaction.ynab.TransactionsApi")
@patch("manager_for_ynab.add_transaction.ynab.ApiClient")
@patch("manager_for_ynab.add_transaction.ynab.Configuration")
@patch("manager_for_ynab.add_transaction.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_add_txn_skips_funding_for_inflow_ready_to_assign(
    sync_mock,
    configuration_cls,
    api_client_cls,
    transactions_api_cls,
    categories_api_cls,
    tmp_path,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)

    transactions_api = transactions_api_cls.return_value
    transactions_api.create_transaction.return_value = None

    assert (
        await add_txn(
            plan_name=None,
            account_name="Checking",
            payee_name="Employer",
            category_name="Inflow: Ready to Assign",
            date=date(2026, 4, 26),
            cleared=None,
            amount=Decimal("12.34"),
            for_real=True,
            quiet=True,
            db=db_path,
            full_refresh=False,
            token_override="token",
        )
        == 0
    )

    sync_mock.assert_awaited_once()
    transactions_api.create_transaction.assert_called_once()
    categories_api_cls.assert_not_called()

    created_wrapper = transactions_api.create_transaction.call_args.args[1]
    assert created_wrapper.transaction.amount == -12340


@patch("manager_for_ynab.add_transaction.ynab.CategoriesApi")
@patch("manager_for_ynab.add_transaction.ynab.TransactionsApi")
@patch("manager_for_ynab.add_transaction.ynab.ApiClient")
@patch("manager_for_ynab.add_transaction.ynab.Configuration")
@patch("manager_for_ynab.add_transaction.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_add_txn_moves_credit_card_payment_back_to_ready_to_assign(
    sync_mock,
    configuration_cls,
    api_client_cls,
    transactions_api_cls,
    categories_api_cls,
    tmp_path,
):
    db_path = tmp_path / "add-transaction-credit-card.sqlite"
    _create_add_transaction_db(db_path)

    transactions_api = transactions_api_cls.return_value
    transactions_api.create_transaction.return_value = None
    categories_api = categories_api_cls.return_value
    categories_api.get_month_category_by_id.return_value = ynab.CategoryResponse(
        data=ynab.CategoryResponseData(
            category=ynab.Category(
                id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
                category_group_id=uuid.UUID("66666666-6666-6666-6666-666666666666"),
                category_group_name="Credit Card Payments",
                name="Credit Card",
                hidden=False,
                budgeted=30000,
                activity=0,
                balance=0,
                deleted=False,
            )
        )
    )

    assert (
        await add_txn(
            plan_name=None,
            account_name="Credit Card",
            payee_name="Employer",
            category_name="Inflow: Ready to Assign",
            date=date(2026, 4, 26),
            cleared=None,
            amount=Decimal("12.34"),
            for_real=True,
            quiet=True,
            db=db_path,
            full_refresh=False,
            token_override="token",
        )
        == 0
    )

    sync_mock.assert_awaited_once()
    transactions_api.create_transaction.assert_called_once()
    categories_api.get_month_category_by_id.assert_called_once()
    categories_api.update_month_category.assert_called_once()

    created_wrapper = transactions_api.create_transaction.call_args.args[1]
    assert created_wrapper.transaction.amount == -12340
    assert (
        categories_api.update_month_category.call_args.kwargs["data"].category.budgeted
        == 17660
    )
