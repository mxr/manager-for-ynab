import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from decimal import Decimal
from enum import Enum
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING
from typing import cast

import aiosqlite
from pyecharts import charts
from pyecharts import options
from pyecharts.commons import utils
from pyecharts.globals import ThemeType
from sqlite_export_for_ynab import default_db_path
from sqlite_export_for_ynab import sync

from manager_for_ynab._auth import resolve_token

if TYPE_CHECKING:
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab sankey"
_READY_TO_ASSIGN = "Inflow: Ready to Assign"
_SANKEY_SQL = files("manager_for_ynab.sankey").joinpath("sankey.sql").read_text()
_MIN_FIGURE_HEIGHT = 1000
_PX_PER_NODE = 30
_NODE_GAP = 24
_MIN_LINK_VALUE_RATIO = 0.02
_PADDED_KEY_PREFIXES = ("category_group:", "category:")
# pyecharts treats ThemeType.DARK as a builtin and never emits a <script> tag for it,
# so echarts.init() silently falls back to the default theme. Load it ourselves.
# https://github.com/pyecharts/pyecharts/issues/2478
_DARK_THEME_SCRIPT = (
    '<script type="text/javascript" '
    'src="https://assets.pyecharts.org/assets/v6/themes/dark.js"></script>'
)
_LABEL_FORMATTER = "function(params) { return params.data.label; }"
_TOOLTIP_FORMATTER = """
function(params) {
    const amount = Number(params.data.amount).toLocaleString(undefined, { style: 'currency', currency: 'USD' });

    if (params.dataType === 'edge') {
        const source = params.data.source_label;
        const target = params.data.target_label;

        return `${source} → ${target}: ${amount}`;
    }

    if (params.data.amount != null) {
        return `${params.data.label}: ${amount}`;
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
    max_stage_size: int


@dataclass(frozen=True)
class SankeyNode:
    key: str
    label: str


class SortBy(Enum):
    ALPHABETICAL = "alphabetical"
    AMOUNT = "amount"


class Theme(Enum):
    LIGHT = "light"
    DARK = "dark"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PACKAGE,
        description="Draw a Sankey diagram for reconciled spending over a date range.",
    )
    parser.add_argument(
        "--start",
        type=_parse_date,
        help="Start date inclusive, in YYYY-MM-DD format or 'today'. Defaults to date of first transaction in budget.",
    )
    parser.add_argument(
        "--end",
        type=_parse_date,
        help="End date inclusive, in YYYY-MM-DD format or 'today'. Defaults to today.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Path to write the ECharts HTML file. Defaults to stdout.",
    )
    parser.add_argument(
        "--sort-by",
        type=SortBy,
        choices=list(SortBy),
        default=SortBy.ALPHABETICAL,
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
    parser.add_argument(
        "--theme",
        type=Theme,
        choices=list(Theme),
        default=Theme.LIGHT,
        help="Color theme to render the Sankey diagram in.",
    )
    return parser


async def run(
    argv: Sequence[str] | None = None, *, token_override: str | None = None
) -> int:
    args = build_parser().parse_args(argv)
    raw_start = cast("date | None", args.start)
    end = cast("date", args.end) or _today()
    if raw_start and raw_start > end:
        build_parser().error("--start must be before or equal to --end")

    return await sankey(
        db=args.sqlite_export_for_ynab_db,
        full_refresh=args.sqlite_export_for_ynab_full_refresh,
        should_sync=args.sync,
        raw_start=raw_start,
        end=end,
        out=args.out,
        sort_by=args.sort_by,
        quiet=args.quiet,
        theme=args.theme,
        token_override=token_override,
    )


async def sankey(
    *,
    db: Path,
    full_refresh: bool,
    should_sync: bool = True,
    raw_start: date | None,
    end: date,
    out: Path | None,
    sort_by: SortBy,
    quiet: bool,
    theme: Theme,
    token_override: str | None,
) -> int:
    token = resolve_token(token_override)

    if should_sync:
        _print("** Refreshing SQLite DB **", quiet=quiet)
        await sync(token, db, full_refresh, quiet=quiet)
        _print("** Done **", quiet=quiet)

    async with aiosqlite.connect(db) as con:
        con.row_factory = aiosqlite.Row
        rows, start = await fetch_sankey(con, raw_start=raw_start, end=end)

    data = build_sankey_data(rows, sort_by=sort_by)
    if not data.values:
        _print("No Sankey data found.", quiet=quiet)
        return 0

    html = build_echarts_html(data, start=start, end=end, theme=theme)
    if out is None:
        sys.stdout.write(html)
    else:
        out.write_text(html)

    return 0


def _print(message: str, *, quiet: bool) -> None:
    if not quiet:
        print(message)


def _parse_date(value: str) -> date:
    if value == "today":
        return _today()
    return date.fromisoformat(value)


def _today() -> date:
    return datetime.now().astimezone().date()


async def fetch_sankey(
    con: aiosqlite.Connection, *, raw_start: date | None, end: date
) -> tuple[list[SankeyRow], date]:
    async with con.execute(
        _SANKEY_SQL,
        ((raw_start or date(1900, 1, 1)).isoformat(), end.isoformat()),
    ) as cur:
        raw_rows = await cur.fetchall()

    rows = [
        SankeyRow(
            payee_name=row["payee_name"] or "Income",
            category_group_id=row["category_group_id"],
            category_group_name=row["category_group_name"],
            category_id=row["category_id"],
            category_name=row["category_name"],
            amount=Decimal(row["amount"]) / Decimal(-1000),
        )
        for row in raw_rows
    ]

    start = min(
        (date.fromisoformat(row["date"]) for row in raw_rows),
        default=datetime.now().astimezone().date(),
    )

    return rows, start


def build_sankey_data(rows: Sequence[SankeyRow], *, sort_by: SortBy) -> SankeyData:
    labels: list[str] = []
    indexes: dict[SankeyNode, int] = {}
    links: defaultdict[tuple[SankeyNode, SankeyNode], Decimal] = defaultdict(Decimal)
    income: defaultdict[SankeyNode, Decimal] = defaultdict(Decimal)
    category_income: defaultdict[SankeyNode, Decimal] = defaultdict(Decimal)
    spending: defaultdict[tuple[SankeyNode, SankeyNode], Decimal] = defaultdict(Decimal)
    spending_payee: defaultdict[tuple[SankeyNode, SankeyNode], Decimal] = defaultdict(
        Decimal
    )
    categories_by_group: defaultdict[SankeyNode, set[SankeyNode]] = defaultdict(set)
    payees_by_category: defaultdict[SankeyNode, set[SankeyNode]] = defaultdict(set)

    def add_node(node: SankeyNode) -> None:
        indexes[node] = len(labels)
        labels.append(node.label)

    ready_to_assign = SankeyNode("ready_to_assign", "Ready to Assign")
    net_category_income = SankeyNode("net_category_income", "Net Category Income")
    income_node = SankeyNode("income", "Income")

    for row in rows:
        if row.amount < 0:
            if row.category_name == _READY_TO_ASSIGN:
                node = SankeyNode(f"income:{row.payee_name}", row.payee_name)
                income[node] += -row.amount
            else:
                node = SankeyNode(
                    f"income_category:{row.category_id}", row.category_name
                )
                category_income[node] += -row.amount
            continue

        if row.amount == 0:
            continue

        category_group = SankeyNode(
            f"category_group:{row.category_group_id}", row.category_group_name
        )
        category = SankeyNode(f"category:{row.category_id}", row.category_name)
        payee = SankeyNode(f"payee:{row.category_id}:{row.payee_name}", row.payee_name)
        spending[(category_group, category)] += row.amount
        spending_payee[(category, payee)] += row.amount
        categories_by_group[category_group].add(category)
        payees_by_category[category].add(payee)

    group_totals = {
        group: sum(
            (spending[(group, category)] for category in categories_by_group[group]),
            Decimal(0),
        )
        for group in categories_by_group
    }
    if sort_by == SortBy.AMOUNT:
        income_nodes = sorted(
            income, key=lambda node: (-income[node], node.label.casefold())
        )
        category_income_nodes = sorted(
            category_income,
            key=lambda node: (-category_income[node], node.label.casefold()),
        )
        group_nodes = sorted(
            categories_by_group,
            key=lambda node: (-group_totals[node], node.label.casefold()),
        )
    else:
        income_nodes = sorted(income, key=lambda node: node.label.casefold())
        category_income_nodes = sorted(
            category_income, key=lambda node: node.label.casefold()
        )
        group_nodes = sorted(
            categories_by_group, key=lambda node: node.label.casefold()
        )

    def sorted_categories(group: SankeyNode) -> list[SankeyNode]:
        if sort_by == SortBy.AMOUNT:
            return sorted(
                categories_by_group[group],
                key=lambda node: (-spending[(group, node)], node.label.casefold()),
            )
        return sorted(
            categories_by_group[group], key=lambda node: node.label.casefold()
        )

    def sorted_payees(category: SankeyNode) -> list[SankeyNode]:
        if sort_by == SortBy.AMOUNT:
            return sorted(
                payees_by_category[category],
                key=lambda node: (
                    -spending_payee[(category, node)],
                    node.label.casefold(),
                ),
            )
        return sorted(
            payees_by_category[category], key=lambda node: node.label.casefold()
        )

    category_nodes = [
        category for group in group_nodes for category in sorted_categories(group)
    ]
    payee_nodes = [
        payee for category in category_nodes for payee in sorted_payees(category)
    ]
    for node in income_nodes:
        add_node(node)
    if income_nodes:
        add_node(ready_to_assign)
    for node in category_income_nodes:
        add_node(node)
    if category_income_nodes:
        add_node(net_category_income)
    add_node(income_node)
    for node in group_nodes:
        add_node(node)
    for node in category_nodes:
        add_node(node)
    for node in payee_nodes:
        add_node(node)

    for node in income_nodes:
        links[(node, ready_to_assign)] += income[node]
    if income_nodes:
        links[(ready_to_assign, income_node)] += sum(
            (income[node] for node in income_nodes), Decimal(0)
        )
    for node in category_income_nodes:
        links[(node, net_category_income)] += category_income[node]
    if category_income_nodes:
        links[(net_category_income, income_node)] += sum(
            (category_income[node] for node in category_income_nodes), Decimal(0)
        )
    for group in group_nodes:
        links[(income_node, group)] += group_totals[group]
        for category in sorted_categories(group):
            links[(group, category)] += spending[(group, category)]
            for payee in sorted_payees(category):
                links[(category, payee)] += spending_payee[(category, payee)]

    sources: list[int] = []
    targets: list[int] = []
    values: list[Decimal] = []
    for (source, target), value in links.items():
        sources.append(indexes[source])
        targets.append(indexes[target])
        values.append(value)

    def padded_count(count: int) -> int:
        return 2 * count - 1 if count else 0

    max_stage_size = max(
        len(income_nodes),
        len(category_income_nodes),
        padded_count(len(group_nodes)),
        padded_count(len(category_nodes)),
        len(payee_nodes),
        1,
    )

    return SankeyData(
        keys=[node.key for node in indexes],
        labels=labels,
        sources=sources,
        targets=targets,
        values=values,
        category_count=len(category_nodes),
        max_stage_size=max_stage_size,
    )


def _node_depths(
    num_nodes: int, sources: Sequence[int], targets: Sequence[int]
) -> list[int]:
    out_edges: list[list[int]] = [[] for _ in range(num_nodes)]
    indegree = [0] * num_nodes
    for source, target in zip(sources, targets, strict=True):
        out_edges[source].append(target)
        indegree[target] += 1

    depths = [0] * num_nodes
    remaining = indegree.copy()
    frontier = [i for i in range(num_nodes) if indegree[i] == 0]
    depth = 0
    while frontier:
        next_frontier: list[int] = []
        for node in frontier:
            depths[node] = depth
            for target in out_edges[node]:
                remaining[target] -= 1
                if remaining[target] == 0:
                    next_frontier.append(target)
        frontier = next_frontier
        depth += 1

    return depths


def _padded_nodes(
    data: SankeyData, amounts: dict[int, Decimal]
) -> list[dict[str, object]]:
    depths = _node_depths(len(data.labels), data.sources, data.targets)
    padded_indexes = {
        prefix: [i for i, key in enumerate(data.keys) if key.startswith(prefix)]
        for prefix in _PADDED_KEY_PREFIXES
    }
    last_padded_index = {
        prefix: indexes[-1] for prefix, indexes in padded_indexes.items() if indexes
    }
    padded_prefix_by_index = {
        i: prefix for prefix, indexes in padded_indexes.items() for i in indexes
    }

    nodes: list[dict[str, object]] = []
    for i, (key, label) in enumerate(zip(data.keys, data.labels, strict=True)):
        nodes.append({"name": key, "label": label, "amount": float(amounts[i])})
        prefix = padded_prefix_by_index.get(i)
        if prefix is not None and i != last_padded_index[prefix]:
            nodes.append(
                {
                    "name": f"__spacer_{prefix}{i}__",
                    "label": "",
                    "value": 0,
                    "depth": depths[i],
                    "itemStyle": {"opacity": 0},
                    "tooltip": {"show": False},
                }
            )

    return nodes


def build_echarts_html(
    data: SankeyData, *, start: date, end: date, theme: Theme
) -> str:
    min_link_value = max(float(value) for value in data.values) * _MIN_LINK_VALUE_RATIO
    figure_height = max(_MIN_FIGURE_HEIGHT, data.max_stage_size * _PX_PER_NODE)

    amounts: dict[int, Decimal] = defaultdict(Decimal)
    for source, target, value in zip(
        data.sources, data.targets, data.values, strict=True
    ):
        amounts[target] += value
        if amounts[source] == 0:
            amounts[source] = value

    return cast(
        "str",
        charts.Sankey(
            init_opts=options.InitOpts(
                width="100%",
                height=f"{figure_height}px",
                **(
                    {
                        "theme": ThemeType.DARK,
                        "bg_color": "#100c2a",
                        "is_fill_bg_color": True,
                    }
                    if theme == Theme.DARK
                    else {}
                ),
            )
        )
        .add(
            "",
            nodes=_padded_nodes(data, amounts),
            links=[
                {
                    "source": data.keys[source],
                    "target": data.keys[target],
                    "source_label": data.labels[source],
                    "target_label": data.labels[target],
                    "amount": float(value),
                    "value": max(float(value), min_link_value),
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
            node_gap=_NODE_GAP,
            pos_top="80px",
            pos_bottom="40px",
        )
        .set_global_opts(
            title_opts=options.TitleOpts(
                title=f"Spending Sankey: {start.isoformat()} to {end.isoformat()}",
                subtitle=f"Generated on {datetime.now().astimezone().date().isoformat()}",
            )
        )
        .render_embed()
        .replace(
            "</head>",
            f"{_DARK_THEME_SCRIPT}\n</head>" if theme == Theme.DARK else "</head>",
        ),
    )


__all__ = [
    "SankeyData",
    "SankeyNode",
    "SankeyRow",
    "build_echarts_html",
    "build_sankey_data",
    "fetch_sankey",
    "run",
    "sankey",
]
