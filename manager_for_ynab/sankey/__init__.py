import argparse
import sys
from collections import defaultdict
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
    payee_name: str
    category_group_id: str
    category_group_name: str
    category_id: str
    category_name: str
    amount: Decimal


@dataclass(frozen=True)
class SankeyData:
    labels: list[str]
    sources: list[int]
    targets: list[int]
    values: list[Decimal]
    x: list[float]
    y: list[float]


@dataclass(frozen=True)
class SankeyNode:
    key: str
    label: str


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
        help="Write HTML to stdout instead of opening the figure with Plotly.",
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
        sys.stdout.write(fig.to_html())
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
            payee_name=row["payee_name"] or "Income",
            category_group_id=row["category_group_id"],
            category_group_name=row["category_group_name"],
            category_id=row["category_id"],
            category_name=row["category_name"],
            amount=Decimal(row["amount"]) / Decimal("-1000"),
        )
        for row in rows
    ]


def build_sankey_data(rows: Sequence[SankeyRow]) -> SankeyData:
    labels: list[str] = []
    indexes: dict[SankeyNode, int] = {}
    x: list[float] = []
    y: list[float] = []
    links: defaultdict[tuple[SankeyNode, SankeyNode], Decimal] = defaultdict(Decimal)
    income: defaultdict[SankeyNode, Decimal] = defaultdict(Decimal)
    spending: defaultdict[tuple[SankeyNode, SankeyNode], Decimal] = defaultdict(Decimal)
    categories_by_group: defaultdict[SankeyNode, set[SankeyNode]] = defaultdict(set)

    def add_node(node: SankeyNode, *, node_x: float, node_y: float) -> None:
        indexes[node] = len(labels)
        labels.append(node.label)
        x.append(node_x)
        y.append(node_y)

    ready_to_assign = SankeyNode("ready_to_assign", "Ready to Assign")

    for row in rows:
        if row.category_name == _READY_TO_ASSIGN and row.amount < 0:
            income[
                SankeyNode(
                    f"income:{row.payee_name or 'Income'}", row.payee_name or "Income"
                )
            ] += -row.amount
            continue

        if row.amount <= 0:
            continue

        category_group = SankeyNode(
            f"category_group:{row.category_group_id}", row.category_group_name
        )
        category = SankeyNode(f"category:{row.category_id}", row.category_name)
        spending[(category_group, category)] += row.amount
        categories_by_group[category_group].add(category)

    income_nodes = sorted(income, key=lambda node: node.label.casefold())
    group_nodes = sorted(categories_by_group, key=lambda node: node.label.casefold())
    category_nodes = [
        category
        for group in group_nodes
        for category in sorted(
            categories_by_group[group], key=lambda node: node.label.casefold()
        )
    ]
    group_totals = {
        group: sum(
            (spending[(group, category)] for category in categories_by_group[group]),
            Decimal(0),
        )
        for group in group_nodes
    }
    income_y = _stacked_y_positions(income_nodes)
    group_y, category_y = _grouped_y_positions(group_nodes, categories_by_group)

    for node in income_nodes:
        add_node(node, node_x=0.0, node_y=income_y[node])
    add_node(ready_to_assign, node_x=0.25, node_y=0.5)
    for node in group_nodes:
        add_node(node, node_x=0.55, node_y=group_y[node])
    for node in category_nodes:
        add_node(node, node_x=1.0, node_y=category_y[node])

    for node in income_nodes:
        links[(node, ready_to_assign)] += income[node]
    for group in group_nodes:
        links[(ready_to_assign, group)] += group_totals[group]
        for category in sorted(
            categories_by_group[group], key=lambda node: node.label.casefold()
        ):
            links[(group, category)] += spending[(group, category)]

    sources: list[int] = []
    targets: list[int] = []
    values: list[Decimal] = []
    for (source, target), value in links.items():
        sources.append(indexes[source])
        targets.append(indexes[target])
        values.append(value)

    return SankeyData(
        labels=labels, sources=sources, targets=targets, values=values, x=x, y=y
    )


def _stacked_y_positions(nodes: Sequence[SankeyNode]) -> dict[SankeyNode, float]:
    return {node: _scale_y(i, len(nodes)) for i, node in enumerate(nodes)}


def _grouped_y_positions(
    group_nodes: Sequence[SankeyNode],
    categories_by_group: defaultdict[SankeyNode, set[SankeyNode]],
) -> tuple[dict[SankeyNode, float], dict[SankeyNode, float]]:
    group_y: dict[SankeyNode, float] = {}
    category_y: dict[SankeyNode, float] = {}
    category_index = 0
    category_count = sum(len(categories_by_group[group]) for group in group_nodes)
    for group in group_nodes:
        group_start = category_index
        sorted_categories = sorted(
            categories_by_group[group], key=lambda node: node.label.casefold()
        )
        for category in sorted_categories:
            category_y[category] = _scale_y(category_index, category_count)
            category_index += 1

        group_midpoint = group_start + ((len(sorted_categories) - 1) / 2)
        group_y[group] = _scale_y(group_midpoint, category_count)

    return group_y, category_y


def _scale_y(index: float, count: int) -> float:
    if count <= 1:
        return 0.5
    return 0.02 + ((index / (count - 1)) * 0.96)


def build_figure(data: SankeyData, *, start: date, end: date) -> go.Figure:
    return go.Figure(
        data=[
            go.Sankey(
                arrangement="fixed",
                valueformat="$,.2f",
                node={"label": data.labels, "x": data.x, "y": data.y},
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
    SankeyNode.__name__,
    SankeyRow.__name__,
    build_figure.__name__,
    build_sankey_data.__name__,
    fetch_sankey_rows.__name__,
    run.__name__,
    sankey.__name__,
]
