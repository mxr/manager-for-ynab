from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest
import pytest_asyncio

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.sankey import build_echarts_html
from manager_for_ynab.sankey import build_sankey_data
from manager_for_ynab.sankey import fetch_sankey_rows
from manager_for_ynab.sankey import run
from manager_for_ynab.sankey import sankey
from manager_for_ynab.sankey import SankeyRow


_SEED_SQL = Path(__file__).with_name("seed.sql")


@pytest_asyncio.fixture
async def db(tmp_path: Path) -> Path:
    path = tmp_path / "db.sqlite"

    async with aiosqlite.connect(path) as con:
        await con.executescript(_SEED_SQL.read_text())
        await con.commit()
    return path


@pytest.mark.asyncio
async def test_fetch_sankey_rows_filters_and_converts_amounts(db):
    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        rows = await fetch_sankey_rows(
            con, start=date(2026, 4, 1), end=date(2026, 4, 30)
        )

    assert rows == [
        SankeyRow("Landlord", "bills-group", "Bills", "rent", "Rent", Decimal("120")),
        SankeyRow(
            "Market", "food-group", "Food", "groceries", "Groceries", Decimal("45.5")
        ),
        SankeyRow(
            "Employer",
            "internal-group",
            "Internal Master Category",
            "ready-to-assign",
            "Inflow: Ready to Assign",
            Decimal("-500"),
        ),
    ]


def test_build_sankey_data_links_income_to_groups_to_categories():
    data = build_sankey_data(
        [
            SankeyRow(
                "Employer",
                "inflow-group",
                "Inflow",
                "ready-to-assign",
                "Inflow: Ready to Assign",
                Decimal("-500"),
            ),
            SankeyRow(
                "Landlord", "bills-group", "Bills", "rent", "Rent", Decimal("120")
            ),
            SankeyRow(
                "Market",
                "food-group",
                "Food",
                "groceries",
                "Groceries",
                Decimal("45.5"),
            ),
        ]
    )

    assert data.labels == [
        "Employer",
        "Ready to Assign",
        "Bills",
        "Food",
        "Rent",
        "Groceries",
    ]
    assert data.sources == [0, 1, 2, 1, 3]
    assert data.targets == [1, 2, 4, 3, 5]
    assert data.values == [
        Decimal("500"),
        Decimal("120"),
        Decimal("120"),
        Decimal("45.5"),
        Decimal("45.5"),
    ]
    assert data.category_count == 2


def test_build_sankey_data_skips_empty_income_and_non_spending_rows():
    data = build_sankey_data(
        [
            SankeyRow(
                "Market",
                "food-group",
                "Food",
                "groceries",
                "Groceries",
                Decimal("-45.5"),
            ),
            SankeyRow(
                "Cafe", "food-group", "Food", "restaurants", "Restaurants", Decimal("0")
            ),
        ]
    )

    assert data == build_sankey_data(())


def test_build_sankey_data_groups_links_over_whole_range():
    data = build_sankey_data(
        [
            SankeyRow(
                "Employer",
                "inflow-group",
                "Inflow",
                "ready-to-assign",
                "Inflow: Ready to Assign",
                Decimal("-500"),
            ),
            SankeyRow(
                "Employer",
                "inflow-group",
                "Inflow",
                "ready-to-assign",
                "Inflow: Ready to Assign",
                Decimal("-300"),
            ),
            SankeyRow(
                "Landlord", "bills-group", "Bills", "rent", "Rent", Decimal("120")
            ),
            SankeyRow(
                "Landlord", "bills-group", "Bills", "rent", "Rent", Decimal("80")
            ),
        ]
    )

    assert data.labels == ["Employer", "Ready to Assign", "Bills", "Rent"]
    assert data.sources == [0, 1, 2]
    assert data.targets == [1, 2, 3]
    assert data.values == [Decimal("800"), Decimal("200"), Decimal("200")]


def test_build_sankey_data_sorts_categories_within_groups_on_right_side():
    data = build_sankey_data(
        [
            SankeyRow(
                "Market", "food-group", "Food", "z-snacks", "Snacks", Decimal("10")
            ),
            SankeyRow(
                "Market",
                "food-group",
                "Food",
                "a-groceries",
                "Groceries",
                Decimal("20"),
            ),
            SankeyRow("Gym", "health-group", "Health", "gym", "Gym", Decimal("30")),
            SankeyRow(
                "Broker",
                "annual-group",
                "Annual Memberships",
                "amazon",
                "Amazon",
                Decimal("40"),
            ),
        ]
    )

    assert data.labels == [
        "Ready to Assign",
        "Annual Memberships",
        "Food",
        "Health",
        "Amazon",
        "Groceries",
        "Snacks",
        "Gym",
    ]
    assert data.category_count == 4


def test_build_sankey_data_keeps_same_named_nodes_separate_by_stage():
    data = build_sankey_data(
        [
            SankeyRow(
                "Employer",
                "inflow-group",
                "Inflow",
                "ready-to-assign",
                "Inflow: Ready to Assign",
                Decimal("-500"),
            ),
            SankeyRow(
                "State",
                "taxes-group",
                "Taxes",
                "taxes-category",
                "Taxes",
                Decimal("120"),
            ),
        ]
    )

    assert data.labels == ["Employer", "Ready to Assign", "Taxes", "Taxes"]
    assert data.sources == [0, 1, 2]
    assert data.targets == [1, 2, 3]
    assert data.values == [Decimal("500"), Decimal("120"), Decimal("120")]


def test_build_echarts_html_uses_node_keys_and_labels():
    data = build_sankey_data(
        [
            SankeyRow(
                "Employer",
                "inflow-group",
                "Inflow",
                "ready-to-assign",
                "Inflow: Ready to Assign",
                Decimal("-500"),
            ),
            SankeyRow(
                "State",
                "taxes-group",
                "Taxes",
                "taxes-category",
                "Taxes",
                Decimal("120"),
            ),
        ]
    )

    html = build_echarts_html(data, start=date(2026, 4, 1), end=date(2026, 4, 30))

    assert "Spending Sankey: 2026-04-01 to 2026-04-30" in html
    assert "category_group:taxes-group" in html
    assert "category:taxes-category" in html
    assert "function(params) { return params.data.label; }" in html
    assert "layoutIterations" in html


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
@patch("manager_for_ynab.sankey.build_echarts_html", return_value="<echarts></echarts>")
@patch("manager_for_ynab.sankey.sync")
@pytest.mark.asyncio
async def test_run_writes_html_to_stdout(sync, build_echarts_html_mock, db, capsys):
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
    out, _ = capsys.readouterr()
    sync.assert_called_once_with("token", db, False, quiet=False)
    build_echarts_html_mock.assert_called_once()
    assert out.endswith("<echarts></echarts>")


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.sankey.build_echarts_html", return_value="<echarts></echarts>")
@patch("manager_for_ynab.sankey.sync")
@pytest.mark.asyncio
async def test_run_no_sync_uses_existing_db(sync, build_echarts_html_mock, db):
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
    build_echarts_html_mock.assert_called_once()


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.sankey.sync")
@pytest.mark.asyncio
async def test_sankey_skips_empty_data(sync, db, capsys):
    ret = await sankey(
        db=db,
        full_refresh=False,
        should_sync=False,
        start=date(2026, 6, 1),
        end=date(2026, 6, 30),
        quiet=False,
        token_override=None,
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_not_called()
    assert out == "No Sankey data found.\n"


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.sankey.sync")
@pytest.mark.asyncio
async def test_sankey_quiet_suppresses_empty_output(sync, db, capsys):
    ret = await sankey(
        db=db,
        full_refresh=False,
        should_sync=False,
        start=date(2026, 6, 1),
        end=date(2026, 6, 30),
        quiet=True,
        token_override=None,
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    sync.assert_not_called()
    assert out == ""
