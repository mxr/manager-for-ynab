import sqlite3
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock
from unittest.mock import patch

import aiosqlite
import pytest
import ynab

import manager_for_ynab.add_transaction as add_transaction_module
from manager_for_ynab.add_transaction import _apply_category_budget_delta
from manager_for_ynab.add_transaction import _choice_prompt
from manager_for_ynab.add_transaction import _fund_category
from manager_for_ynab.add_transaction import _load_account_by_id
from manager_for_ynab.add_transaction import _prompt
from manager_for_ynab.add_transaction import _resolve_account_id
from manager_for_ynab.add_transaction import _resolve_category
from manager_for_ynab.add_transaction import _resolve_credit_card_payment_category
from manager_for_ynab.add_transaction import _resolve_payee
from manager_for_ynab.add_transaction import _resolve_transaction
from manager_for_ynab.add_transaction import amount_prompt
from manager_for_ynab.add_transaction import build_parser
from manager_for_ynab.add_transaction import confirm
from manager_for_ynab.add_transaction import date_prompt
from manager_for_ynab.add_transaction import decimal
from manager_for_ynab.add_transaction import edit_distance
from manager_for_ynab.add_transaction import run


def _create_add_transaction_db(path: Path) -> None:
    seed_path = Path(__file__).parents[2] / "testing" / "seed.sql"
    contents = seed_path.read_text()
    with sqlite3.connect(path) as con:
        con.executescript(contents)


def _seed_ids(path: Path) -> dict[str, str]:
    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        return {
            "plan_id": con.execute("SELECT id FROM plans").fetchone()["id"],
            "checking_account_id": con.execute(
                "SELECT id FROM accounts WHERE name = 'Checking'"
            ).fetchone()["id"],
            "credit_card_account_id": con.execute(
                "SELECT id FROM accounts WHERE name = 'Credit Card'"
            ).fetchone()["id"],
            "employer_payee_id": con.execute(
                "SELECT id FROM payees WHERE name = 'Employer'"
            ).fetchone()["id"],
            "ready_to_assign_category_id": con.execute(
                "SELECT id FROM categories WHERE name = 'Inflow: Ready to Assign'"
            ).fetchone()["id"],
            "credit_card_category_id": con.execute(
                "SELECT id FROM categories WHERE name = 'Credit Card'"
            ).fetchone()["id"],
        }


@pytest.fixture
def resolved_dining_transaction():
    return add_transaction_module.ResolvedTransaction(
        plan=add_transaction_module.ResolvedPlan(
            id="11111111-1111-1111-1111-111111111111",
            name="My Plan",
        ),
        account=add_transaction_module.ResolvedAccount(
            id="22222222-2222-2222-2222-222222222222",
            name="Checking",
            type="checking",
        ),
        payee=add_transaction_module.ResolvedPayee(
            id="33333333-3333-3333-3333-333333333333",
            name="Employer",
        ),
        category=add_transaction_module.ResolvedCategory(
            id="44444444-4444-4444-4444-444444444444",
            name="Dining Out",
        ),
        date=date(2026, 4, 26),
        cleared=ynab.TransactionClearedStatus.UNCLEARED,
        amount=Decimal("12.34"),
    )


def test_build_parser_uses_expected_prog():
    assert build_parser().prog == "manager-for-ynab add-transaction"


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        pytest.param("kitten", "sitting", 3, id="classic-example"),
        pytest.param("", "abc", 3, id="empty-left"),
        pytest.param("abc", "", 3, id="empty-right"),
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
async def test_add_transaction_skips_funding_for_inflow_ready_to_assign(
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
        await add_transaction(
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
async def test_add_transaction_moves_credit_card_payment_back_to_ready_to_assign(
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
        await add_transaction(
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


@patch(
    "manager_for_ynab.add_transaction.add_transaction_and_move_funds",
    new_callable=AsyncMock,
)
@patch(
    "manager_for_ynab.add_transaction.sync_and_resolve_transaction",
    new_callable=AsyncMock,
)
@patch("manager_for_ynab.add_transaction.resolve_token")
@pytest.mark.asyncio
async def test_run_delegates_parsed_args(
    resolve_token_mock,
    sync_and_resolve_transaction_mock,
    add_transaction_and_move_funds_mock,
):
    resolve_token_mock.return_value = "resolved-token"
    sync_and_resolve_transaction_mock.return_value = object()
    add_transaction_and_move_funds_mock.return_value = 17

    ret = await run(
        (
            "--plan-name",
            "My Plan",
            "--account-name",
            "Checking",
            "--payee-name",
            "Employer",
            "--category-name",
            "Inflow: Ready to Assign",
            "--date",
            "2026-04-26",
            "--cleared",
            "uncleared",
            "--amount",
            "12.34",
            "--for-real",
            "--quiet",
            "--sqlite-export-for-ynab-db",
            "/tmp/db.sqlite",
            "--sqlite-export-for-ynab-full-refresh",
        )
    )

    assert ret == 17
    resolve_token_mock.assert_called_once_with(None)
    sync_and_resolve_transaction_mock.assert_awaited_once()
    kwargs = sync_and_resolve_transaction_mock.await_args.kwargs
    assert kwargs["plan_name"] == "My Plan"
    assert kwargs["account_name"] == "Checking"
    assert kwargs["payee_name"] == "Employer"
    assert kwargs["category_name"] == "Inflow: Ready to Assign"
    assert kwargs["date"] == date(2026, 4, 26)
    assert kwargs["cleared"].name == "UNCLEARED"
    assert kwargs["amount"] == Decimal("12.34")
    assert kwargs["db"] == Path("/tmp/db.sqlite")
    assert kwargs["full_refresh"] is True
    assert kwargs["token"] == "resolved-token"
    assert kwargs["quiet"] is True

    add_transaction_and_move_funds_mock.assert_awaited_once()
    kwargs = add_transaction_and_move_funds_mock.await_args.kwargs
    assert kwargs["resolved"] is sync_and_resolve_transaction_mock.return_value
    assert kwargs["token"] == "resolved-token"
    assert kwargs["db"] == Path("/tmp/db.sqlite")
    assert kwargs["for_real"] is True
    assert kwargs["quiet"] is True


@pytest.mark.parametrize(
    "err",
    [
        pytest.param(RuntimeError("runtime boom"), id="runtime-error"),
        pytest.param(ValueError("value boom"), id="value-error"),
    ],
)
@patch(
    "manager_for_ynab.add_transaction.sync_and_resolve_transaction",
    new_callable=AsyncMock,
)
@patch("manager_for_ynab.add_transaction.resolve_token")
@pytest.mark.asyncio
async def test_run_returns_one_when_resolution_stage_fails(
    resolve_token_mock,
    sync_and_resolve_transaction_mock,
    err,
    capsys,
):
    resolve_token_mock.return_value = "resolved-token"
    sync_and_resolve_transaction_mock.side_effect = err

    ret = await run(())

    out, stderr = capsys.readouterr()
    assert ret == 1
    assert out == f"{err}\n"
    assert stderr == ""


@pytest.mark.parametrize(
    ("quiet", "expected_output"),
    [
        pytest.param(False, "Dry run, not creating transaction:", id="verbose"),
        pytest.param(True, "", id="quiet"),
    ],
)
@patch("manager_for_ynab.add_transaction.ynab.TransactionsApi")
@patch("manager_for_ynab.add_transaction.ynab.ApiClient")
@patch("manager_for_ynab.add_transaction.ynab.Configuration")
@patch("manager_for_ynab.add_transaction.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_add_transaction_dry_run(
    sync_mock,
    configuration_cls,
    api_client_cls,
    transactions_api_cls,
    quiet,
    expected_output,
    tmp_path,
    capsys,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)

    ret = await add_transaction(
        plan_name=None,
        account_name="Checking",
        payee_name="Employer",
        category_name="Inflow: Ready to Assign",
        date=date(2026, 4, 26),
        cleared=None,
        amount=Decimal("12.34"),
        for_real=False,
        quiet=quiet,
        db=db_path,
        full_refresh=False,
        token_override="token",
    )

    out, err = capsys.readouterr()
    assert ret == 0
    if quiet:
        assert out == expected_output
    else:
        assert expected_output in out
    assert err == ""
    sync_mock.assert_awaited_once()
    configuration_cls.assert_not_called()
    api_client_cls.assert_not_called()
    transactions_api_cls.assert_not_called()


@patch(
    "manager_for_ynab.add_transaction._apply_category_budget_delta",
    new_callable=AsyncMock,
)
@patch("manager_for_ynab.add_transaction.ynab.TransactionsApi")
@patch("manager_for_ynab.add_transaction.ynab.ApiClient")
@patch("manager_for_ynab.add_transaction.ynab.Configuration")
@patch("manager_for_ynab.add_transaction.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_add_transaction_reports_ready_to_assign_credit_card_payment(
    sync_mock,
    configuration_cls,
    api_client_cls,
    transactions_api_cls,
    apply_category_budget_delta_mock,
    tmp_path,
    capsys,
):
    db_path = tmp_path / "add-transaction-credit-card-positive.sqlite"
    _create_add_transaction_db(db_path)
    apply_category_budget_delta_mock.return_value = 12340

    ret = await add_transaction(
        plan_name="My Plan",
        account_name="Credit Card",
        payee_name="Employer",
        category_name="Inflow: Ready to Assign",
        date=date(2026, 4, 26),
        cleared=None,
        amount=Decimal("12.34"),
        for_real=True,
        quiet=False,
        db=db_path,
        full_refresh=False,
        token_override="token",
    )

    out, err = capsys.readouterr()
    assert ret == 0
    assert err == ""
    sync_mock.assert_awaited_once()
    transactions_api_cls.return_value.create_transaction.assert_called_once()
    apply_category_budget_delta_mock.assert_awaited_once()
    assert "Created transaction:" in out
    assert "Applied 12.34 USD to 'Credit Card' from Ready to Assign." in out


@patch("manager_for_ynab.add_transaction.ynab.CategoriesApi")
@patch("manager_for_ynab.add_transaction.ynab.TransactionsApi")
@patch("manager_for_ynab.add_transaction.ynab.ApiClient")
@patch("manager_for_ynab.add_transaction.ynab.Configuration")
@patch("manager_for_ynab.add_transaction.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_add_transaction_reports_returned_credit_card_payment(
    sync_mock,
    configuration_cls,
    api_client_cls,
    transactions_api_cls,
    categories_api_cls,
    tmp_path,
    capsys,
):
    db_path = tmp_path / "add-transaction-credit-card-negative.sqlite"
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

    ret = await add_transaction(
        plan_name=None,
        account_name="Credit Card",
        payee_name="Employer",
        category_name="Inflow: Ready to Assign",
        date=date(2026, 4, 26),
        cleared=None,
        amount=Decimal("12.34"),
        for_real=True,
        quiet=False,
        db=db_path,
        full_refresh=False,
        token_override="token",
    )

    out, err = capsys.readouterr()
    assert ret == 0
    assert err == ""
    sync_mock.assert_awaited_once()
    transactions_api.create_transaction.assert_called_once()
    categories_api.get_month_category_by_id.assert_called_once()
    categories_api.update_month_category.assert_called_once()
    assert "Returned 12.34 USD from 'Credit Card' to Ready to Assign." in out


@patch(
    "manager_for_ynab.add_transaction._apply_category_budget_delta",
    new_callable=AsyncMock,
)
@patch("manager_for_ynab.add_transaction.ynab.TransactionsApi")
@patch("manager_for_ynab.add_transaction.ynab.ApiClient")
@patch("manager_for_ynab.add_transaction.ynab.Configuration")
@patch("manager_for_ynab.add_transaction.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_add_transaction_reports_returned_budget_delta(
    sync_mock,
    configuration_cls,
    api_client_cls,
    transactions_api_cls,
    apply_category_budget_delta_mock,
    tmp_path,
    capsys,
):
    db_path = tmp_path / "add-transaction-credit-card-returned.sqlite"
    _create_add_transaction_db(db_path)
    transactions_api = transactions_api_cls.return_value
    transactions_api.create_transaction.return_value = None
    apply_category_budget_delta_mock.return_value = -12340

    ret = await add_transaction(
        plan_name=None,
        account_name="Credit Card",
        payee_name="Employer",
        category_name="Inflow: Ready to Assign",
        date=date(2026, 4, 26),
        cleared=None,
        amount=Decimal("12.34"),
        for_real=True,
        quiet=False,
        db=db_path,
        full_refresh=False,
        token_override="token",
    )

    out, err = capsys.readouterr()
    assert ret == 0
    assert err == ""
    sync_mock.assert_awaited_once()
    transactions_api.create_transaction.assert_called_once()
    apply_category_budget_delta_mock.assert_awaited_once()
    assert "Returned 12.34 USD from 'Credit Card' to Ready to Assign." in out


@patch("manager_for_ynab.add_transaction._fund_category", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction.ynab.TransactionsApi")
@patch("manager_for_ynab.add_transaction.ynab.ApiClient")
@patch("manager_for_ynab.add_transaction.ynab.Configuration")
@patch("manager_for_ynab.add_transaction.sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_add_transaction_funds_category_from_ready_to_assign(
    sync_mock,
    configuration_cls,
    api_client_cls,
    transactions_api_cls,
    fund_category_mock,
    tmp_path,
    capsys,
):
    db_path = tmp_path / "add-transaction-category.sqlite"
    _create_add_transaction_db(db_path)
    ids = _seed_ids(db_path)
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT INTO categories VALUES (?, ?, 0, 'Dining', 'Dining Out')",
            (str(uuid.uuid4()), ids["plan_id"]),
        )

    fund_category_mock.return_value = 5000

    ret = await add_transaction(
        plan_name="My Plan",
        account_name="Checking",
        payee_name="Employer",
        category_name="Dining Out",
        date=date(2026, 4, 26),
        cleared=None,
        amount=Decimal("12.34"),
        for_real=True,
        quiet=False,
        db=db_path,
        full_refresh=False,
        token_override="token",
    )

    out, err = capsys.readouterr()
    assert ret == 0
    assert err == ""
    sync_mock.assert_awaited_once()
    transactions_api_cls.return_value.create_transaction.assert_called_once()
    fund_category_mock.assert_awaited_once()
    assert "Created transaction:" in out
    assert "Funded 'Dining Out' from 'Ready to Assign' by 5.00 USD" in out


@patch(
    "manager_for_ynab.add_transaction.resolve_token", side_effect=RuntimeError("boom")
)
@pytest.mark.asyncio
async def test_add_transaction_raises_when_token_resolution_fails(
    resolve_token_mock, tmp_path
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)

    with pytest.raises(RuntimeError, match="boom"):
        await add_transaction(
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
            token_override=None,
        )


@patch("manager_for_ynab.add_transaction.sync", new_callable=AsyncMock)
@patch(
    "manager_for_ynab.add_transaction._resolve_transaction",
    side_effect=ValueError("boom"),
)
@patch("manager_for_ynab.add_transaction.resolve_token")
@pytest.mark.asyncio
async def test_add_transaction_returns_one_when_transaction_resolution_fails(
    resolve_token_mock,
    resolve_transaction_mock,
    sync_mock,
    tmp_path,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    resolve_token_mock.return_value = "token"

    assert (
        await add_transaction(
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
            token_override=None,
        )
        == 1
    )


@patch("manager_for_ynab.add_transaction.sync", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction.ynab.TransactionsApi")
@patch("manager_for_ynab.add_transaction.ynab.ApiClient")
@patch("manager_for_ynab.add_transaction.ynab.Configuration")
@pytest.mark.asyncio
async def test_add_transaction_returns_one_when_api_raises(
    configuration_cls,
    api_client_cls,
    transactions_api_cls,
    sync_mock,
    tmp_path,
    capsys,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    transactions_api = transactions_api_cls.return_value
    transactions_api.create_transaction.side_effect = ynab.ApiException(
        status=500, reason="boom"
    )

    ret = await add_transaction(
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

    out, err = capsys.readouterr()
    assert ret == 1
    assert out == ""
    assert "Failed to create transaction:" in err
    sync_mock.assert_awaited_once()
    configuration_cls.assert_called_once_with(access_token="token")
    api_client_cls.assert_called_once_with(configuration_cls.return_value)


@pytest.mark.parametrize(
    "err",
    [
        pytest.param(RuntimeError("runtime boom"), id="runtime-error"),
        pytest.param(ValueError("value boom"), id="value-error"),
    ],
)
@patch("manager_for_ynab.add_transaction._fund_category", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction.ynab.TransactionsApi")
@patch("manager_for_ynab.add_transaction.ynab.ApiClient")
@patch("manager_for_ynab.add_transaction.ynab.Configuration")
@pytest.mark.asyncio
async def test_add_transaction_and_move_funds_returns_one_when_funding_fails(
    configuration_cls,
    api_client_cls,
    transactions_api_cls,
    fund_category_mock,
    err,
    resolved_dining_transaction,
    tmp_path,
    capsys,
):
    fund_category_mock.side_effect = err

    ret = await add_transaction_module.add_transaction_and_move_funds(
        resolved=resolved_dining_transaction,
        token="token",
        db=tmp_path / "add-transaction.sqlite",
        for_real=True,
        quiet=True,
    )

    out, stderr = capsys.readouterr()
    assert ret == 1
    assert out == f"{err}\n"
    assert stderr == ""
    transactions_api_cls.return_value.create_transaction.assert_called_once()
    configuration_cls.assert_called_once_with(access_token="token")
    api_client_cls.assert_called_once_with(configuration_cls.return_value)


@patch("manager_for_ynab.add_transaction.sync", new_callable=AsyncMock)
@patch(
    "manager_for_ynab.add_transaction._resolve_transaction",
    side_effect=RuntimeError("boom"),
)
@patch("manager_for_ynab.add_transaction.resolve_token")
@pytest.mark.asyncio
async def test_add_transaction_returns_one_when_runtime_error_is_raised(
    resolve_token_mock,
    resolve_transaction_mock,
    sync_mock,
    tmp_path,
    capsys,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    resolve_token_mock.return_value = "token"

    ret = await add_transaction(
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
        token_override=None,
    )

    out, err = capsys.readouterr()
    assert ret == 1
    assert out == "boom\n"
    assert err == ""
    sync_mock.assert_awaited_once()


@patch("manager_for_ynab.add_transaction._load_name_to_id", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_transaction_errors_when_no_plans(load_name_to_id_mock, tmp_path):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    load_name_to_id_mock.return_value = {}

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError, match="No plans found in this YNAB account."):
            await _resolve_transaction(
                con,
                plan_name=None,
                account_name="Checking",
                payee_name="Employer",
                category_name="Inflow: Ready to Assign",
                date=date(2026, 4, 26),
                cleared=None,
                amount=Decimal("12.34"),
            )


@patch("manager_for_ynab.add_transaction.date_prompt", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction.amount_prompt", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._choice_prompt", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_transaction_prompts_for_missing_values(
    choice_prompt_mock,
    amount_prompt_mock,
    date_prompt_mock,
    tmp_path,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    ids = _seed_ids(db_path)
    choice_prompt_mock.side_effect = [
        "Checking",
        "Employer",
        "Inflow: Ready to Assign",
    ]
    date_prompt_mock.return_value = date(2026, 4, 26)
    amount_prompt_mock.return_value = Decimal("12.34")

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        resolved = await _resolve_transaction(
            con,
            plan_name=None,
            account_name=None,
            payee_name=None,
            category_name=None,
            date=None,
            cleared=None,
            amount=None,
        )

    assert resolved.plan.id == ids["plan_id"]
    assert resolved.account.id == ids["checking_account_id"]
    assert resolved.payee.id == ids["employer_payee_id"]
    assert resolved.category is not None
    assert resolved.category.id == ids["ready_to_assign_category_id"]
    assert resolved.date == date(2026, 4, 26)
    assert resolved.amount == Decimal("12.34")


@patch("manager_for_ynab.add_transaction._resolve_payee", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._resolve_category", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._load_account_by_id", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._resolve_account_id", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._choice_prompt", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._load_name_to_id", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_transaction_prompts_for_plan_when_multiple_plans(
    load_name_to_id_mock,
    choice_prompt_mock,
    resolve_account_id_mock,
    load_account_by_id_mock,
    resolve_category_mock,
    resolve_payee_mock,
    tmp_path,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    load_name_to_id_mock.return_value = {"Plan A": "plan-a", "Plan B": "plan-b"}
    choice_prompt_mock.return_value = "Plan B"
    resolve_account_id_mock.return_value = "account-id"
    load_account_by_id_mock.return_value = ("Checking", "checking")
    resolve_payee_mock.return_value = ("payee-id", "Employer", None)
    resolve_category_mock.return_value = ("category-id", "Dining Out")

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        resolved = await _resolve_transaction(
            con,
            plan_name=None,
            account_name="Checking",
            payee_name="Employer",
            category_name="Dining Out",
            date=date(2026, 4, 26),
            cleared=None,
            amount=Decimal("12.34"),
        )

    assert resolved.plan.id == "plan-b"
    assert resolved.plan.name == "Plan B"


@patch("manager_for_ynab.add_transaction._resolve_payee", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._load_account_by_id", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._resolve_account_id", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._load_name_to_id", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_transaction_allows_transfer_without_category(
    load_name_to_id_mock,
    resolve_account_id_mock,
    load_account_by_id_mock,
    resolve_payee_mock,
    tmp_path,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    load_name_to_id_mock.return_value = {"My Plan": "plan-id"}
    resolve_account_id_mock.return_value = "account-id"
    load_account_by_id_mock.return_value = ("Checking", "checking")
    resolve_payee_mock.return_value = ("payee-id", "Transfer", "transfer-account-id")

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        resolved = await _resolve_transaction(
            con,
            plan_name=None,
            account_name="Checking",
            payee_name="Transfer",
            category_name=None,
            date=date(2026, 4, 26),
            cleared=None,
            amount=Decimal("12.34"),
        )

    assert resolved.category is None


@patch("manager_for_ynab.add_transaction._matching_entry", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._resolve_payee", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_transaction_rejects_category_for_transfer(
    resolve_payee_mock,
    matching_entry_mock,
    tmp_path,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    ids = _seed_ids(db_path)
    matching_entry_mock.return_value = ids["checking_account_id"]
    resolve_payee_mock.return_value = ("payee-id", "Transfer", "transfer-account-id")

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(
            ValueError, match="Category not allowed for transfer transactions"
        ):
            await _resolve_transaction(
                con,
                plan_name=None,
                account_name="Checking",
                payee_name="Transfer",
                category_name="Dining Out",
                date=date(2026, 4, 26),
                cleared=None,
                amount=Decimal("12.34"),
            )

    resolve_payee_mock.assert_awaited_once()


@patch("manager_for_ynab.add_transaction._prompt", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_shared_prompt_helpers_use_prompt_value(prompt_mock):
    prompt_mock.side_effect = ["Checking", "2026-04-26", "12.34", "yes"]

    assert await _choice_prompt("Account: ", {"Checking": "account-id"}) == "Checking"
    assert await date_prompt() == date(2026, 4, 26)
    assert await amount_prompt() == Decimal("12.34")
    assert await confirm("Proceed?") is True


@patch("manager_for_ynab.add_transaction.PromptSession")
@pytest.mark.asyncio
async def test_prompt_uses_prompt_session(prompt_session_cls):
    session = prompt_session_cls.return_value
    session.prompt_async = AsyncMock(return_value="value")

    assert await _prompt("Message: ", lambda text: True, default="ignored") == "value"
    session.prompt_async.assert_awaited_once()


@patch("manager_for_ynab.add_transaction._choice_prompt", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_account_id_prompts_when_missing(choice_prompt_mock, tmp_path):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    ids = _seed_ids(db_path)
    choice_prompt_mock.return_value = "Checking"

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        account_id = await _resolve_account_id(con, ids["plan_id"], None)

    assert account_id == ids["checking_account_id"]


@patch("manager_for_ynab.add_transaction._load_name_to_id", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_account_id_errors_without_accounts(
    load_name_to_id_mock, tmp_path
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    load_name_to_id_mock.return_value = {}

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError, match="No accounts found in this plan."):
            await _resolve_account_id(con, "plan-id", None)


@patch("manager_for_ynab.add_transaction._choice_prompt", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_category_prompts_when_missing(choice_prompt_mock, tmp_path):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    ids = _seed_ids(db_path)
    choice_prompt_mock.return_value = "Inflow: Ready to Assign"

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        category_id, category_name = await _resolve_category(con, ids["plan_id"], None)

    assert category_id == ids["ready_to_assign_category_id"]
    assert category_name == "Inflow: Ready to Assign"


@patch("manager_for_ynab.add_transaction._load_name_to_id", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_category_errors_without_categories(
    load_name_to_id_mock, tmp_path
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    load_name_to_id_mock.return_value = {}

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError, match="No categories found in this plan."):
            await _resolve_category(con, "plan-id", None)


@patch("manager_for_ynab.add_transaction._choice_prompt", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_payee_prompts_when_missing(choice_prompt_mock, tmp_path):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    ids = _seed_ids(db_path)
    choice_prompt_mock.return_value = "Employer"

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        payee_id, payee_name, transfer_account_id = await _resolve_payee(
            con, ids["plan_id"], None
        )

    assert payee_id == ids["employer_payee_id"]
    assert payee_name == "Employer"
    assert transfer_account_id is None


@pytest.mark.asyncio
async def test_resolve_payee_returns_fuzzy_match(tmp_path):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    ids = _seed_ids(db_path)

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        await con.create_function("EDITDISTANCE", 2, edit_distance)
        payee_id, payee_name, transfer_account_id = await _resolve_payee(
            con, ids["plan_id"], "Employe"
        )

    assert payee_id == ids["employer_payee_id"]
    assert payee_name == "Employer"
    assert transfer_account_id is None


@pytest.mark.parametrize(
    ("payee_name", "closest_match", "expected_error"),
    [
        pytest.param(
            "New Payee",
            ("payee-id", "Employer", False, 1),
            "Payee 'New Payee' was not created",
            id="closest-match",
        ),
        pytest.param(
            "Unknown",
            None,
            "Payee 'Unknown' was not created",
            id="no-closest-match",
        ),
    ],
)
@patch("manager_for_ynab.add_transaction.confirm", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._closest_match", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._matching_entry", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._load_payees", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_payee_rejects_new_payee(
    load_payees_mock,
    matching_entry_mock,
    closest_match_mock,
    confirm_mock,
    payee_name,
    closest_match,
    expected_error,
    tmp_path,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    load_payees_mock.return_value = [("Employer", "payee-id", None)]
    matching_entry_mock.side_effect = ValueError("No close match")
    closest_match_mock.return_value = closest_match
    confirm_mock.return_value = False

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(ValueError, match=expected_error):
            await _resolve_payee(con, "plan-id", payee_name)


@patch("manager_for_ynab.add_transaction.confirm", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._closest_match", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._matching_entry", new_callable=AsyncMock)
@patch("manager_for_ynab.add_transaction._load_payees", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_resolve_payee_allows_new_payee(
    load_payees_mock,
    matching_entry_mock,
    closest_match_mock,
    confirm_mock,
    tmp_path,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    load_payees_mock.return_value = [("Employer", "payee-id", None)]
    matching_entry_mock.side_effect = ValueError("No close match")
    closest_match_mock.return_value = ("payee-id", "Employer", False, 1)
    confirm_mock.return_value = True

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        payee_id, payee_name, transfer_account_id = await _resolve_payee(
            con, "plan-id", "New Payee"
        )

    assert payee_id is None
    assert payee_name == "New Payee"
    assert transfer_account_id is None


@pytest.mark.asyncio
async def test_resolve_payee_returns_existing_transfer_payee(tmp_path):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    ids = _seed_ids(db_path)
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT INTO payees VALUES (?, ?, 0, ?, ?)",
            (
                str(uuid.uuid4()),
                ids["plan_id"],
                "Transfer",
                ids["checking_account_id"],
            ),
        )

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        payee_id, payee_name, transfer_account_id = await _resolve_payee(
            con, ids["plan_id"], "Transfer"
        )

    assert payee_id is not None
    assert payee_name == "Transfer"
    assert transfer_account_id == ids["checking_account_id"]


@pytest.mark.asyncio
async def test_resolve_payee_errors_when_no_payees(tmp_path):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    with sqlite3.connect(db_path) as con:
        con.execute("DELETE FROM payees")

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError, match="No payees found in this plan."):
            await _resolve_payee(con, "plan-id", None)


@pytest.mark.asyncio
async def test_matching_entry_raises_when_no_rows(tmp_path):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    with sqlite3.connect(db_path) as con:
        con.execute("DELETE FROM payees")

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        await con.create_function("EDITDISTANCE", 2, edit_distance)
        with pytest.raises(ValueError, match="No entries found in payees"):
            await add_transaction_module._matching_entry(con, "payees", "Alpha")


@pytest.mark.asyncio
async def test_matching_entry_rejects_distant_match(tmp_path):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        await con.create_function("EDITDISTANCE", 2, edit_distance)
        with pytest.raises(ValueError, match="No close match for 'zzz' in 'accounts'."):
            await add_transaction_module._matching_entry(con, "accounts", "zzz")


@pytest.mark.asyncio
async def test_load_account_by_id_errors_for_missing_account(tmp_path):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(RuntimeError, match="No account found with id 'missing'."):
            await _load_account_by_id(con, "missing")


@pytest.mark.asyncio
async def test_resolve_credit_card_payment_category_errors_for_missing_and_duplicate_rows(
    tmp_path,
):
    db_path = tmp_path / "add-transaction.sqlite"
    _create_add_transaction_db(db_path)
    ids = _seed_ids(db_path)

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(
            RuntimeError,
            match="No credit card payment category found for account 'missing'.",
        ):
            await _resolve_credit_card_payment_category(con, ids["plan_id"], "missing")

    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT INTO categories VALUES (?, ?, 0, 'Credit Card Payments', 'Credit Card')",
            (str(uuid.uuid4()), ids["plan_id"]),
        )

    async with aiosqlite.connect(db_path) as con:
        con.row_factory = aiosqlite.Row
        with pytest.raises(
            RuntimeError,
            match="Found 2 credit card payment categories for account 'Credit Card'.",
        ):
            await _resolve_credit_card_payment_category(
                con, ids["plan_id"], "Credit Card"
            )


@pytest.mark.asyncio
async def test_apply_category_budget_delta_zero_short_circuits():
    api_client = cast("ynab.ApiClient", object())
    assert (
        await _apply_category_budget_delta(
            api_client=api_client,
            plan_id="plan-id",
            date=date(2026, 4, 26),
            category_id="category-id",
            budget_delta=0,
        )
        == 0
    )


@patch(
    "manager_for_ynab.add_transaction._apply_category_budget_delta",
    new_callable=AsyncMock,
)
@pytest.mark.asyncio
async def test_fund_category_converts_negative_amount_to_positive_budget_delta(
    apply_category_budget_delta_mock,
):
    apply_category_budget_delta_mock.return_value = 12340
    api_client = cast("ynab.ApiClient", object())

    assert (
        await _fund_category(
            api_client=api_client,
            plan_id="plan-id",
            date=date(2026, 4, 26),
            category_id="category-id",
            amount=-12340,
        )
        == 12340
    )
    apply_category_budget_delta_mock.assert_awaited_once_with(
        api_client, "plan-id", date(2026, 4, 26), "category-id", 12340
    )
