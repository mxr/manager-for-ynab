import argparse
import asyncio
import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import ynab

from manager_for_ynab._auth import resolve_token

if TYPE_CHECKING:
    from collections.abc import Generator
    from collections.abc import Sequence


_PACKAGE = "manager-for-ynab zero-out"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PACKAGE,
        description="Zero out planned amount for a category from a start year-month through the end month.",
    )
    parser.add_argument(
        "--plan-id",
        help="YNAB plan ID. If omitted, uses the most recently updated one.",
    )
    parser.add_argument(
        "--category-group",
        help="Category group name pattern to scope the category lookup.",
    )
    parser.add_argument(
        "--category-name",
        required=True,
        help="Category name pattern to update.",
    )
    parser.add_argument(
        "--start",
        type=parse_year_month,
        required=True,
        help="Start year-month (e.g. 2025-01).",
    )
    parser.add_argument(
        "--end",
        type=parse_year_month,
        help="End year-month inclusive (e.g. 2025-06). Defaults to current month.",
    )
    parser.add_argument(
        "--for-real",
        action="store_true",
        help="Apply the updates instead of only previewing them.",
    )
    return parser


def parse_year_month(raw: str) -> tuple[int, int]:
    year, month = tuple(map(int, raw.split("-")))
    if month < 1 or month > 12:
        raise argparse.ArgumentTypeError(f"Invalid month in {raw!r}. Expected YYYY-MM.")
    return year, month


def month_range(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> Generator[tuple[int, int]]:
    return (
        (year, month0 + 1)
        for year, month0 in (
            divmod(i, 12)
            for i in range(start_year * 12 + start_month - 1, end_year * 12 + end_month)
        )
    )


def format_months(months: tuple[tuple[int, int], ...]) -> list[str]:
    return [f"{year}-{month:02d}" for year, month in months]


def _normalize_like_pattern(pattern: str) -> str:
    if "%" in pattern or "_" in pattern:
        return pattern
    return f"%{pattern}%"


def _like_match(value: str, pattern: str) -> bool:
    like_pattern = _normalize_like_pattern(pattern).casefold()
    value = value.casefold()
    value_len = len(value)
    pattern_len = len(like_pattern)
    dp = [[False] * (pattern_len + 1) for _ in range(value_len + 1)]
    dp[0][0] = True

    for pattern_idx, char in enumerate(like_pattern, start=1):
        if char == "%":
            dp[0][pattern_idx] = dp[0][pattern_idx - 1]

    for value_idx in range(1, value_len + 1):
        for pattern_idx in range(1, pattern_len + 1):
            char = like_pattern[pattern_idx - 1]
            if char == "%":
                dp[value_idx][pattern_idx] = (
                    dp[value_idx][pattern_idx - 1] or dp[value_idx - 1][pattern_idx]
                )
            elif char == "_" or char == value[value_idx - 1]:
                dp[value_idx][pattern_idx] = dp[value_idx - 1][pattern_idx - 1]

    return dp[value_len][pattern_len]


def _update_month_category(
    categories_api: ynab.CategoriesApi,
    plan_id: str,
    category_id: str,
    year: int,
    month: int,
) -> tuple[str, str | None]:
    month_str = f"{year}-{month:02d}"
    try:
        categories_api.update_month_category(
            plan_id=plan_id,
            month=datetime.date(year, month, 1),
            category_id=category_id,
            data=ynab.PatchMonthCategoryWrapper(
                category=ynab.SaveMonthCategory(budgeted=0)
            ),
        )
        return month_str, None
    except ynab.ApiException as e:
        return month_str, f"{e}"


def _get_plan(plans_api: ynab.PlansApi, plan_id: str | None) -> tuple[str, str]:
    try:
        plans_response = plans_api.get_plans()
    except ynab.ApiException as e:
        raise RuntimeError(f"Failed to fetch plans: {e}") from e

    plans = plans_response.data.plans
    if not plans:
        raise RuntimeError("No plans found in this YNAB account.")

    if plan_id:
        for plan in plans:
            if str(plan.id) == plan_id:
                return plan_id, plan.name
        return plan_id, plan_id

    plan = max(plans, key=lambda b: b.last_modified_on or datetime.datetime.min)
    return str(plan.id), plan.name


def _get_category_id(
    categories_api: ynab.CategoriesApi,
    plan_id: str,
    category_group: str | None,
    category_name: str,
) -> tuple[str, str, str]:
    try:
        cats_resp = categories_api.get_categories(plan_id)
    except ynab.ApiException as e:
        raise RuntimeError(f"Failed to fetch categories: {e}") from e

    matching = [
        (group, category)
        for group in cats_resp.data.category_groups
        for category in group.categories
        if (category_group is None or _like_match(group.name, category_group))
        and _like_match(category.name, category_name)
    ]
    if len(matching) == 0:
        if category_group:
            raise RuntimeError(
                f"No category matching LIKE '{_normalize_like_pattern(category_name)}' found in group matching LIKE '{_normalize_like_pattern(category_group)}'."
            )
        raise RuntimeError(
            f"No category matching LIKE '{_normalize_like_pattern(category_name)}' found in this plan."
        )
    if len(matching) > 1:
        names = ", ".join(
            f"{group.name} / {category.name}" for group, category in matching
        )
        if category_group:
            raise RuntimeError(
                f"Found {len(matching)} categories matching LIKE '{_normalize_like_pattern(category_name)}' in group matching LIKE '{_normalize_like_pattern(category_group)}' - {names}."
            )
        raise RuntimeError(
            f"Found {len(matching)} categories matching LIKE '{_normalize_like_pattern(category_name)}' - {names}. Try again with --category-group."
        )

    group, category = matching[0]
    return str(category.id), category.name, group.name


async def _run_updates(
    categories_api: ynab.CategoriesApi,
    plan_id: str,
    category_id: str,
    months: tuple[tuple[int, int], ...],
) -> None:
    with ThreadPoolExecutor(max_workers=5) as executor:
        tasks = tuple(
            asyncio.get_running_loop().run_in_executor(
                executor,
                _update_month_category,
                categories_api,
                plan_id,
                category_id,
                year,
                month,
            )
            for year, month in months
        )
        for task in tasks:
            month_str, err = await task
            if err is None:
                print(f"{month_str}: set planned to 0.")
            else:
                print(f"Failed to update month {month_str}: {err}")


def run(argv: Sequence[str] | None = None, *, token_override: str | None = None) -> int:
    args = build_parser().parse_args(argv)

    token = resolve_token(token_override)

    configuration = ynab.Configuration(access_token=token)

    with ynab.ApiClient(configuration) as api_client:
        plans_api = ynab.PlansApi(api_client)
        categories_api = ynab.CategoriesApi(api_client)

        try:
            plan_id, plan_name = _get_plan(plans_api, args.plan_id)
            category_id, category_name, category_group = _get_category_id(
                categories_api, plan_id, args.category_group, args.category_name
            )
        except RuntimeError as e:
            print(e)
            return 1

        print(f"Targeting {category_group} - {category_name} from plan {plan_name}")

        start_year, start_month = args.start
        if args.end:
            end_year, end_month = args.end
        else:
            today = datetime.date.today()
            end_year, end_month = today.year, today.month

        months = tuple(month_range(start_year, start_month, end_year, end_month))
        month_labels = format_months(months)
        if not month_labels:
            print("No months selected.")
            return 0

        print("Months to update:", ", ".join(month_labels))
        if not args.for_real:
            print("Use --for-real to actually update categories.")
            return 0

        asyncio.run(_run_updates(categories_api, plan_id, category_id, months))

    print("Done.")
    return 0


__all__ = [run.__name__]
