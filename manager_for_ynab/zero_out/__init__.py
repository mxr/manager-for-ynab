import argparse
import asyncio
import datetime
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import ynab

if TYPE_CHECKING:
    from collections.abc import Generator
    from collections.abc import Sequence


_ENV_TOKEN = "YNAB_PERSONAL_ACCESS_TOKEN"
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
        "--category-name",
        required=True,
        help="Category name to update (matched with a regex but must match uniquely).",
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


def _get_plan_id(plans_api: ynab.PlansApi, plan_id: str | None) -> str:
    if plan_id:
        return plan_id

    try:
        plans_response = plans_api.get_plans()
    except ynab.ApiException as e:
        raise RuntimeError(f"Failed to fetch plans: {e}") from e

    plans = plans_response.data.plans
    if not plans:
        raise RuntimeError("No plans found in this YNAB account.")

    plan = max(plans, key=lambda b: b.last_modified_on or datetime.datetime.min)
    print(f"Using plan: {plan.name} ({plan.id})")
    return str(plan.id)


def _get_category_id(
    categories_api: ynab.CategoriesApi, plan_id: str, category_name: str
) -> tuple[str, str]:
    try:
        cats_resp = categories_api.get_categories(plan_id)
    except ynab.ApiException as e:
        raise RuntimeError(f"Failed to fetch categories: {e}") from e

    matching = [
        category
        for group in cats_resp.data.category_groups
        for category in group.categories
        if re.search(category_name, category.name, re.IGNORECASE)
    ]
    if len(matching) != 1:
        names = ", ".join(category.name for category in matching)
        raise RuntimeError(
            f"Found {len(matching)} categories matching '{category_name}' - {names}."
        )

    category = matching[0]
    return str(category.id), category.name


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


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    token = os.environ.get(_ENV_TOKEN)
    if not token:
        raise ValueError(
            "Must set YNAB access token as `YNAB_PERSONAL_ACCESS_TOKEN` environment variable. See https://api.ynab.com/#personal-access-tokens"
        )

    configuration = ynab.Configuration(access_token=token)

    with ynab.ApiClient(configuration) as api_client:
        plans_api = ynab.PlansApi(api_client)
        categories_api = ynab.CategoriesApi(api_client)

        try:
            plan_id = _get_plan_id(plans_api, args.plan_id)
            category_id, category_name = _get_category_id(
                categories_api, plan_id, args.category_name
            )
        except RuntimeError as e:
            print(e)
            return 1

        print(f"Using category: {category_name} ({category_id})")

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
