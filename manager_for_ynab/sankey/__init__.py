import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite
import plotly.graph_objects as go
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync

from manager_for_ynab._auth import resolve_token

if TYPE_CHECKING:
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab sankey"
_READY_TO_ASSIGN = "Inflow: Ready to Assign"
_SANKEY_SQL = files("manager_for_ynab.sankey").joinpath("sankey.sql").read_text()


@dataclass(frozen=True)
class SankeyRow:
    category_group_name: str
    category_name: str
    amount: Decimal


@dataclass(frozen=True)
class SankeyData:
    labels: list[str]
    sources: list[int]
    targets: list[int]
    values: list[Decimal]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PACKAGE,
        description="Draw a Sankey diagram for reconciled spending over a date range.",
    )
    parser.add_argument(
        "--start",
        type=date.fromisoformat,
        required=True,
        help="Start date inclusive, in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        required=True,
        help="End date inclusive, in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--html",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write sankey.html instead of opening the figure with Plotly.",
    )
    parser.add_argument(
        "--sqlite-export-for-ynab-db",
        type=Path,
        default=default_db_path(),
        help="Path to sqlite-export-for-ynab SQLite DB file.",
    )
    parser.add_argument(
        "--sqlite-export-for-ynab-full-refresh",
        action="store_true",
        help="Whether to refresh the SQLite DB from scratch.",
    )
    parser.add_argument(
        "--sync",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Refresh the SQLite DB before using it.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress sync and status output.",
    )
    return parser


async def run(
    argv: Sequence[str] | None = None, *, token_override: str | None = None
) -> int:
    args = build_parser().parse_args(argv)
    if args.start > args.end:
        build_parser().error("--start must be before or equal to --end")

    return await sankey(
        db=args.sqlite_export_for_ynab_db,
        full_refresh=args.sqlite_export_for_ynab_full_refresh,
        should_sync=args.sync,
        start=args.start,
        end=args.end,
        html=args.html,
        quiet=args.quiet,
        token_override=token_override,
    )


async def sankey(
    *,
    db: Path,
    full_refresh: bool,
    should_sync: bool = True,
    start: date,
    end: date,
    html: bool,
    quiet: bool,
    token_override: str | None,
) -> int:
    token = resolve_token(token_override)

    if should_sync:
        _print("** Refreshing SQLite DB **", quiet=quiet)
        await sync(token, db, full_refresh, quiet=quiet)
        _print("** Done **", quiet=quiet)

    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        rows = await fetch_sankey_rows(con, start=start, end=end)

    data = build_sankey_data(rows)
    if not data.values:
        _print("No Sankey data found.", quiet=quiet)
        return 0

    fig = build_figure(data, start=start, end=end)
    if html:
        fig.write_html("sankey.html")
        _print("Wrote sankey.html.", quiet=quiet)
    else:
        fig.show()

    return 0


def _print(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message)


async def fetch_sankey_rows(
    con: aiosqlite.Connection, *, start: date, end: date
) -> list[SankeyRow]:
    async with con.execute(_SANKEY_SQL, (start.isoformat(), end.isoformat())) as cur:
        rows = await cur.fetchall()

    return [
        SankeyRow(
            category_group_name=row["category_group_name"],
            category_name=row["category_name"],
            amount=Decimal(row["amount"]) / Decimal("-1000"),
        )
        for row in rows
    ]


def build_sankey_data(rows: Sequence[SankeyRow]) -> SankeyData:
    labels: list[str] = []
    indexes: dict[str, int] = {}
    sources: list[int] = []
    targets: list[int] = []
    values: list[Decimal] = []

    def index(label: str) -> int:
        if label not in indexes:
            indexes[label] = len(labels)
            labels.append(label)
        return indexes[label]

    def link(source: str, target: str, value: Decimal) -> None:
        if value == 0:
            return
        sources.append(index(source))
        targets.append(index(target))
        values.append(value)

    income = sum(
        (
            -row.amount
            for row in rows
            if row.category_name == _READY_TO_ASSIGN and row.amount < 0
        ),
        Decimal(0),
    )
    link("Income", "Ready to Assign", income)

    for row in rows:
        if row.category_name == _READY_TO_ASSIGN or row.amount <= 0:
            continue
        link("Ready to Assign", row.category_group_name, row.amount)
        link(row.category_group_name, row.category_name, row.amount)

    return SankeyData(labels=labels, sources=sources, targets=targets, values=values)


def build_figure(data: SankeyData, *, start: date, end: date) -> go.Figure:
    return go.Figure(
        data=[
            go.Sankey(
                node={"label": data.labels},
                link={
                    "source": data.sources,
                    "target": data.targets,
                    "value": [float(value) for value in data.values],
                },
            )
        ],
        layout={
            "title_text": f"Spending Sankey: {start.isoformat()} to {end.isoformat()}"
        },
    )


__all__ = [
    SankeyData.__name__,
    SankeyRow.__name__,
    build_figure.__name__,
    build_sankey_data.__name__,
    fetch_sankey_rows.__name__,
    run.__name__,
    sankey.__name__,
]
