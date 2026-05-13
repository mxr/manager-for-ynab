import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import plotly.graph_objects as go
import pytest

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.sankey import build_sankey_data
from manager_for_ynab.sankey import fetch_sankey_rows
from manager_for_ynab.sankey import run
from manager_for_ynab.sankey import sankey
from manager_for_ynab.sankey import SankeyRow


@pytest.fixture
def db(tmpdir) -> Path:
    path = Path(tmpdir) / "db.sqlite"
    with sqlite3.connect(path) as con:
        con.execute(
            """
            CREATE TABLE flat_transactions (
                category_group_name TEXT
                , category_name TEXT
                , amount INT
                , cleared TEXT
                , "date" TEXT
                , payee_name TEXT
            )
            """
        )
        con.executemany(
            """
            INSERT INTO flat_transactions VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "Inflow",
                    "Inflow: Ready to Assign",
                    500000,
                    "reconciled",
                    "2026-04-01",
                    "Employer",
                ),
                ("Bills", "Rent", -120000, "reconciled", "2026-04-02", "Landlord"),
                ("Food", "Groceries", -45500, "Reconciled", "2026-04-03", "Market"),
                ("Food", "Restaurants", -20000, "cleared", "2026-04-03", "Cafe"),
                (
                    "Internal Master Category",
                    "Hidden",
                    -10000,
                    "reconciled",
                    "2026-04-03",
                    "Hidden",
                ),
                ("Bills", "Rent", -10000, "reconciled", "2026-05-01", "Landlord"),
                (
                    "Inflow",
                    "Inflow: Ready to Assign",
                    100000,
                    "reconciled",
                    "2026-04-04",
                    "Starting Balance",
                ),
            ),
        )
    return path


@pytest.mark.asyncio
async def test_fetch_sankey_rows_filters_and_converts_amounts(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        rows = await fetch_sankey_rows(
            con, start=date(2026, 4, 1), end=date(2026, 4, 30)
        )

    assert rows == [
        SankeyRow("Bills", "Rent", Decimal("120")),
        SankeyRow("Food", "Groceries", Decimal("45.5")),
        SankeyRow("Inflow", "Inflow: Ready to Assign", Decimal("-500")),
    ]


def test_build_sankey_data_links_income_to_groups_to_categories():
    data = build_sankey_data(
        [
            SankeyRow("Inflow", "Inflow: Ready to Assign", Decimal("-500")),
            SankeyRow("Bills", "Rent", Decimal("120")),
            SankeyRow("Food", "Groceries", Decimal("45.5")),
        ]
    )

    assert data.labels == [
        "Income",
        "Ready to Assign",
        "Bills",
        "Rent",
        "Food",
        "Groceries",
    ]
    assert data.sources == [0, 1, 2, 1, 4]
    assert data.targets == [1, 2, 3, 4, 5]
    assert data.values == [
        Decimal("500"),
        Decimal("120"),
        Decimal("120"),
        Decimal("45.5"),
        Decimal("45.5"),
    ]


def test_build_sankey_data_skips_empty_income_and_non_spending_rows():
    data = build_sankey_data(
        [
            SankeyRow("Food", "Groceries", Decimal("-45.5")),
            SankeyRow("Food", "Restaurants", Decimal("0")),
        ]
    )

    assert data == build_sankey_data(())


@pytest.mark.asyncio
async def test_run_rejects_end_before_start(db):
    with pytest.raises(SystemExit) as excinfo:
        await run(
            (
                "--sqlite-export-for-ynab-db",
                str(db),
                "--start",
                "2026-04-30",
                "--end",
                "2026-04-01",
            )
        )

    assert excinfo.value.code == 2


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.sankey.sync")
@patch.object(go.Figure, "show", autospec=True)
@pytest.mark.asyncio
async def test_run_defaults_to_show(show, sync, db):
    ret = await run(
        (
            "--sqlite-export-for-ynab-db",
            str(db),
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-30",
        )
    )

    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=False)
    show.assert_called_once()


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.sankey.sync")
@patch.object(go.Figure, "write_html", autospec=True)
@pytest.mark.asyncio
async def test_run_html_writes_file(write_html, sync, db):
    ret = await run(
        (
            "--sqlite-export-for-ynab-db",
            str(db),
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-30",
            "--html",
        )
    )

    assert ret == 0
    sync.assert_called_once_with("token", db, False, quiet=False)
    write_html.assert_called_once()
    assert write_html.call_args.args[1] == "sankey.html"


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.sankey.sync")
@patch.object(go.Figure, "show", autospec=True)
@pytest.mark.asyncio
async def test_run_no_sync_uses_existing_db(show, sync, db):
    ret = await run(
        (
            "--sqlite-export-for-ynab-db",
            str(db),
            "--start",
            "2026-04-01",
            "--end",
            "2026-04-30",
            "--no-sync",
        )
    )

    assert ret == 0
    sync.assert_not_called()
    show.assert_called_once()


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.sankey.sync")
@patch.object(go.Figure, "show", autospec=True)
@pytest.mark.asyncio
async def test_sankey_skips_empty_data(show, sync, db, capsys):
    ret = await sankey(
        db=db,
        full_refresh=False,
        should_sync=False,
        start=date(2026, 6, 1),
        end=date(2026, 6, 30),
        html=False,
        quiet=False,
        token_override=None,
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_not_called()
    show.assert_not_called()
    assert out == "No Sankey data found.\n"


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.sankey.sync")
@patch.object(go.Figure, "show", autospec=True)
@pytest.mark.asyncio
async def test_sankey_quiet_suppresses_empty_output(show, sync, db, capsys):
    ret = await sankey(
        db=db,
        full_refresh=False,
        should_sync=False,
        start=date(2026, 6, 1),
        end=date(2026, 6, 30),
        html=False,
        quiet=True,
        token_override=None,
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_not_called()
    show.assert_not_called()
    assert out == ""
