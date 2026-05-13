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
from pyecharts import charts
from pyecharts import options
from pyecharts.commons import utils
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync

from manager_for_ynab._auth import resolve_token

if TYPE_CHECKING:
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab sankey"
_READY_TO_ASSIGN = "Inflow: Ready to Assign"
_SANKEY_SQL = files("manager_for_ynab.sankey").joinpath("sankey.sql").read_text()
_MIN_FIGURE_HEIGHT = 1000
_LABEL_FORMATTER = "function(params) { return params.data.label; }"
_TOOLTIP_FORMATTER = """
function(params) {
    if (params.dataType === 'edge') {
        return params.data.source_label + ' -> ' + params.data.target_label + ': ' + Number(params.data.value).toLocaleString(undefined, {style: 'currency', currency: 'USD'});
    }
    return params.data.label;
}
"""


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
    keys: list[str]
    labels: list[str]
    sources: list[int]
    targets: list[int]
    values: list[Decimal]
    category_count: int


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
        "--out",
        type=Path,
        help="Path to write the ECharts HTML file. Defaults to stdout.",
    )
    parser.add_argument(
        "--sort-by",
        choices=("alphabetical", "amount"),
        default="alphabetical",
        help="How to sort Sankey nodes within each stage.",
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
        out=args.out,
        sort_by=args.sort_by,
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
    out: Path | None,
    sort_by: str,
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

    data = build_sankey_data(rows, sort_by=sort_by)
    if not data.values:
        _print("No Sankey data found.", quiet=quiet)
        return 0

    html = build_echarts_html(data, start=start, end=end)
    if out is None:
        sys.stdout.write(html)
    else:
        out.write_text(html)

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


def build_sankey_data(
    rows: Sequence[SankeyRow], *, sort_by: str = "alphabetical"
) -> SankeyData:
    labels: list[str] = []
    indexes: dict[SankeyNode, int] = {}
    links: defaultdict[tuple[SankeyNode, SankeyNode], Decimal] = defaultdict(Decimal)
    income: defaultdict[SankeyNode, Decimal] = defaultdict(Decimal)
    spending: defaultdict[tuple[SankeyNode, SankeyNode], Decimal] = defaultdict(Decimal)
    categories_by_group: defaultdict[SankeyNode, set[SankeyNode]] = defaultdict(set)

    def add_node(node: SankeyNode) -> None:
        indexes[node] = len(labels)
        labels.append(node.label)

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

    if sort_by not in {"alphabetical", "amount"}:
        msg = "sort_by must be 'alphabetical' or 'amount'"
        raise ValueError(msg)

    group_totals = {
        group: sum(
            (spending[(group, category)] for category in categories_by_group[group]),
            Decimal(0),
        )
        for group in categories_by_group
    }
    if sort_by == "amount":
        income_nodes = sorted(
            income, key=lambda node: (-income[node], node.label.casefold())
        )
        group_nodes = sorted(
            categories_by_group,
            key=lambda node: (-group_totals[node], node.label.casefold()),
        )
    else:
        income_nodes = sorted(income, key=lambda node: node.label.casefold())
        group_nodes = sorted(
            categories_by_group, key=lambda node: node.label.casefold()
        )

    def sorted_categories(group: SankeyNode) -> list[SankeyNode]:
        if sort_by == "amount":
            return sorted(
                categories_by_group[group],
                key=lambda node: (-spending[(group, node)], node.label.casefold()),
            )
        return sorted(
            categories_by_group[group], key=lambda node: node.label.casefold()
        )

    category_nodes = [
        category for group in group_nodes for category in sorted_categories(group)
    ]
    for node in income_nodes:
        add_node(node)
    add_node(ready_to_assign)
    for node in group_nodes:
        add_node(node)
    for node in category_nodes:
        add_node(node)

    for node in income_nodes:
        links[(node, ready_to_assign)] += income[node]
    for group in group_nodes:
        links[(ready_to_assign, group)] += group_totals[group]
        for category in sorted_categories(group):
            links[(group, category)] += spending[(group, category)]

    sources: list[int] = []
    targets: list[int] = []
    values: list[Decimal] = []
    for (source, target), value in links.items():
        sources.append(indexes[source])
        targets.append(indexes[target])
        values.append(value)

    return SankeyData(
        keys=[node.key for node in indexes],
        labels=labels,
        sources=sources,
        targets=targets,
        values=values,
        category_count=len(category_nodes),
    )


def build_echarts_html(data: SankeyData, *, start: date, end: date) -> str:
    return (
        charts.Sankey(
            init_opts=options.InitOpts(width="100%", height=f"{_MIN_FIGURE_HEIGHT}px")
        )
        .add(
            "",
            nodes=[
                {"name": key, "label": label}
                for key, label in zip(data.keys, data.labels, strict=True)
            ],
            links=[
                {
                    "source": data.keys[source],
                    "target": data.keys[target],
                    "source_label": data.labels[source],
                    "target_label": data.labels[target],
                    "value": float(value),
                }
                for source, target, value in zip(
                    data.sources, data.targets, data.values, strict=True
                )
            ],
            label_opts=options.LabelOpts(formatter=utils.JsCode(_LABEL_FORMATTER)),
            tooltip_opts=options.TooltipOpts(
                formatter=utils.JsCode(_TOOLTIP_FORMATTER)
            ),
            layout_iterations=0,
            node_gap=10,
        )
        .set_global_opts(
            title_opts=options.TitleOpts(
                title=f"Spending Sankey: {start.isoformat()} to {end.isoformat()}"
            )
        )
        .render_embed()
    )


__all__ = [
    SankeyData.__name__,
    SankeyNode.__name__,
    SankeyRow.__name__,
    build_echarts_html.__name__,
    build_sankey_data.__name__,
    fetch_sankey_rows.__name__,
    run.__name__,
    sankey.__name__,
]
