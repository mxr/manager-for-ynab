import argparse
import asyncio
import datetime
from typing import Any
from typing import cast
from typing import Literal
from unittest.mock import patch

import pytest
import ynab

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.zero_out import _get_category_id
from manager_for_ynab.zero_out import _get_plan
from manager_for_ynab.zero_out import _regex_search
from manager_for_ynab.zero_out import _run_updates
from manager_for_ynab.zero_out import _update_month_category
from manager_for_ynab.zero_out import month_range
from manager_for_ynab.zero_out import parse_year_month
from manager_for_ynab.zero_out import run

REAL_DATE = datetime.date
pytest_plugins = ("tests.zero_out.fixtures",)


def test_month_range_is_inclusive():
    assert tuple(month_range(2025, 11, 2026, 2)) == (
        (2025, 11),
        (2025, 12),
        (2026, 1),
        (2026, 2),
    )


def test_parse_year_month_rejects_invalid_month():
    with pytest.raises(argparse.ArgumentTypeError):
        parse_year_month("2025-13")


@pytest.mark.parametrize(
    ("value", "pattern", "expected"),
    [
        pytest.param("Medical", "med", True, id="substring-search"),
        pytest.param("True Expenses", "^true", True, id="anchored-search"),
        pytest.param("Rent 2", r"Rent \d", True, id="digit-search"),
        pytest.param("Rent 20", r"^Rent \d$", False, id="anchored-non-match"),
    ],
)
def test_regex_search(value, pattern, expected):
    assert _regex_search(value, pattern) is expected


def test_get_plan_uses_latest_plan(plans_api, plan_summary, plan_summary_response):
    response = plan_summary_response(
        [
            plan_summary("Old", last_modified_on=datetime.datetime(2025, 1, 1)),
            plan_summary("New", last_modified_on=datetime.datetime(2025, 2, 1)),
        ]
    )

    plans_api.get_plans.return_value = response

    assert _get_plan(plans_api, None) == (str(response.data.plans[1].id), "New")


def test_get_plan_uses_explicit_plan_id(plans_api, plan_summary, plan_summary_response):
    plan = plan_summary("Chosen", last_modified_on=datetime.datetime(2025, 2, 1))

    plans_api.get_plans.return_value = plan_summary_response([plan])

    assert _get_plan(plans_api, str(plan.id)) == (str(plan.id), "Chosen")


def test_get_plan_errors_when_explicit_plan_id_is_missing(
    plans_api, plan_summary, plan_summary_response
):
    response = plan_summary_response(
        [plan_summary("Other", last_modified_on=datetime.datetime(2025, 2, 1))]
    )

    plans_api.get_plans.return_value = response

    with pytest.raises(RuntimeError) as excinfo:
        _get_plan(plans_api, "plan-123")

    assert str(excinfo.value) == "No plan found with id 'plan-123'."


def test_get_plan_wraps_api_exception(plans_api):
    plans_api.get_plans.side_effect = ynab.ApiException(status=500, reason="boom")

    with pytest.raises(RuntimeError) as excinfo:
        _get_plan(plans_api, None)

    assert "Failed to fetch plans" in str(excinfo.value)


def test_get_plan_errors_when_plan_list_is_empty(plans_api, plan_summary_response):
    plans_api.get_plans.return_value = plan_summary_response([])

    with pytest.raises(RuntimeError) as excinfo:
        _get_plan(plans_api, None)

    assert "No plans found" in str(excinfo.value)


@pytest.mark.parametrize(
    ("category_group_pattern", "category_name", "group_specs", "expected"),
    [
        pytest.param(
            None,
            "Rent",
            [("Fixed", ["Rent"])],
            ("Rent", "Fixed"),
            id="substring-name-without-group",
        ),
        pytest.param(
            "Vari",
            "rent",
            [
                ("Fixed", ["Rent"]),
                ("Variable", ["Rent"]),
            ],
            ("Rent", "Variable"),
            id="substring-group-and-name",
        ),
        pytest.param(
            "^Var",
            r"Ren.",
            [
                ("Fixed", ["Rent"]),
                ("Variable", ["Rent"]),
            ],
            ("Rent", "Variable"),
            id="explicit-regex-patterns",
        ),
    ],
)
def test_get_category_id_matches_plan_categories(
    categories_api,
    category_group,
    categories_response,
    category_group_pattern,
    category_name,
    group_specs,
    expected,
):
    groups = [
        category_group(group_name, category_names)
        for group_name, category_names in group_specs
    ]
    categories_api.get_categories.return_value = categories_response(groups)

    category_id, matched_name, matched_group = _get_category_id(
        categories_api, "plan-1", category_group_pattern, category_name
    )

    expected_name, expected_group = expected
    expected_category = next(
        category
        for group in groups
        if group.name == expected_group
        for category in group.categories
        if category.name == expected_name
    )
    assert category_id == str(expected_category.id)
    assert matched_name == expected_name
    assert matched_group == expected_group


@pytest.mark.parametrize(
    ("category_group_pattern", "category_name", "group_specs", "expected_message"),
    [
        pytest.param(
            None,
            "Rent",
            [
                ("Fixed", ["Rent"]),
                ("Variable", ["Rent"]),
            ],
            "Found 2 categories matching regex 'Rent'",
            id="ambiguous-name",
        ),
        pytest.param(
            "Fixed",
            "Rent",
            [("Fixed", ["Rent", "Rent 2"])],
            "Found 2 categories matching regex 'Rent' in group matching regex 'Fixed'",
            id="ambiguous-regex-in-group",
        ),
        pytest.param(
            "Variable",
            "Rent",
            [("Fixed", ["Rent"])],
            "No category matching regex 'Rent' found in group matching regex 'Variable'.",
            id="missing-in-group",
        ),
        pytest.param(
            None,
            "Groceries",
            [("Fixed", ["Rent"])],
            "No category matching regex 'Groceries' found in this plan.",
            id="missing-in-plan",
        ),
        pytest.param(
            None,
            "Rent",
            [],
            "No category matching regex 'Rent' found in this plan.",
            id="missing-in-empty-plan",
        ),
    ],
)
def test_get_category_id_errors(
    categories_api,
    category_group,
    categories_response,
    category_group_pattern,
    category_name,
    group_specs,
    expected_message,
):
    groups = [
        category_group(group_name, category_names)
        for group_name, category_names in group_specs
    ]
    categories_api.get_categories.return_value = categories_response(groups)

    with pytest.raises(RuntimeError) as excinfo:
        _get_category_id(
            categories_api, "plan-1", category_group_pattern, category_name
        )

    assert expected_message in str(excinfo.value)


def test_get_category_id_wraps_api_exception(categories_api):
    categories_api.get_categories.side_effect = ynab.ApiException(
        status=500, reason="boom"
    )

    with pytest.raises(RuntimeError) as excinfo:
        _get_category_id(categories_api, "plan-1", None, "rent")

    assert "Failed to fetch categories" in str(excinfo.value)


@pytest.mark.parametrize(
    ("update_error", "expected"),
    [
        pytest.param(None, ("2025-02", None), id="success"),
        pytest.param(
            ynab.ApiException(status=400, reason="bad request"),
            ("2025-02", "error"),
            id="api-error",
        ),
    ],
)
def test_update_month_category(categories_api, update_error, expected):
    categories_api.update_month_category.side_effect = update_error

    month_str, error = _update_month_category(
        categories_api, "plan-1", "cat-1", 2025, 2
    )

    assert month_str == expected[0]
    if expected[1] is None:
        assert error is None
        categories_api.update_month_category.assert_called_once()
        _, kwargs = categories_api.update_month_category.call_args
        assert kwargs["plan_id"] == "plan-1"
        assert kwargs["category_id"] == "cat-1"
    else:
        assert error is not None


@pytest.mark.asyncio
@patch.object(asyncio, "get_running_loop")
@patch("manager_for_ynab.zero_out.ThreadPoolExecutor")
async def test_run_updates_prints_success_and_failure(
    thread_pool_executor, get_running_loop, capsys
):
    class FakeExecutor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> Literal[False]:
            return False

    class FakeLoop:
        def __init__(self):
            self.calls = 0

        def run_in_executor(
            self, executor, func, categories_api, plan_id, category_id, year, month
        ):
            self.calls += 1
            result = ("2025-01", None) if self.calls == 1 else ("2025-02", "boom")
            return asyncio.create_task(asyncio.sleep(0, result=result))

    fake_loop = FakeLoop()
    thread_pool_executor.side_effect = lambda max_workers: FakeExecutor()
    get_running_loop.return_value = fake_loop

    await _run_updates(cast("Any", object()), "plan-1", "cat-1", ((2025, 1), (2025, 2)))

    out, _ = capsys.readouterr()
    assert "2025-01: set planned to 0." in out
    assert "Failed to update month 2025-02: boom" in out


@patch.dict("os.environ", {_ENV_TOKEN: ""})
def test_run_requires_token():
    # patch.dict mutates os.environ before resolve_token reads it.

    with pytest.raises(ValueError) as excinfo:
        run(("--category-name", "Rent", "--start", "2025-01"))

    assert "Must set YNAB access token" in str(excinfo.value)


@patch("manager_for_ynab.zero_out._run_updates")
def test_run_uses_token_override(
    run_updates,
    capsys,
    ynab_configuration,
    ynab_api_client,
    ynab_plans_api,
    ynab_categories_api,
    plan_summary,
    plan_summary_response,
    category_group,
    categories_response,
):
    plans = [plan_summary("New", last_modified_on=datetime.datetime(2025, 2, 1))]
    category_groups = [category_group("Fixed", ["Rent"])]
    ynab_plans_api.get_plans.return_value = plan_summary_response(plans)
    ynab_categories_api.get_categories.return_value = categories_response(
        category_groups
    )
    run_updates.side_effect = AssertionError(
        "_run_updates should not run during dry-run"
    )

    ret = run(
        ("--category-name", "Rent", "--start", "2025-01", "--end", "2025-02"),
        token_override="override-token",
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    ynab_configuration.assert_called_once_with(access_token="override-token")
    ynab_api_client.assert_called_once_with(ynab_configuration.return_value)
    assert "Targeting Fixed - Rent from plan New" in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.zero_out._run_updates")
def test_run_dry_run_prints_preview(
    run_updates,
    capsys,
    ynab_configuration,
    ynab_api_client,
    ynab_plans_api,
    ynab_categories_api,
    plan_summary,
    plan_summary_response,
    category_group,
    categories_response,
):
    plans = [plan_summary("New", last_modified_on=datetime.datetime(2025, 2, 1))]
    category_groups = [category_group("Fixed", ["Rent"])]
    ynab_plans_api.get_plans.return_value = plan_summary_response(plans)
    ynab_categories_api.get_categories.return_value = categories_response(
        category_groups
    )
    run_updates.side_effect = AssertionError(
        "_run_updates should not run during dry-run"
    )

    ret = run(("--category-name", "Rent", "--start", "2025-01", "--end", "2025-02"))

    out, _ = capsys.readouterr()
    assert ret == 0
    ynab_configuration.assert_called_once_with(access_token="token")
    ynab_api_client.assert_called_once_with(ynab_configuration.return_value)
    assert "Targeting Fixed - Rent from plan New" in out
    assert "Months to update: 2025-01, 2025-02" in out
    assert "Use --for-real to actually update categories." in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.zero_out._get_plan")
def test_run_returns_error_when_plan_lookup_fails(
    get_plan,
    capsys,
    ynab_configuration,
    ynab_api_client,
    ynab_plans_api,
    ynab_categories_api,
):
    get_plan.side_effect = RuntimeError("bad plan")

    ret = run(("--category-name", "Rent", "--start", "2025-01"))

    out, _ = capsys.readouterr()
    assert ret == 1
    ynab_configuration.assert_called_once_with(access_token="token")
    ynab_api_client.assert_called_once_with(ynab_configuration.return_value)
    assert "bad plan" in out


@pytest.mark.parametrize(
    ("argv", "today", "expected"),
    [
        pytest.param(
            ("--category-name", "Rent", "--start", "2025-03", "--end", "2025-02"),
            None,
            "No months selected.",
            id="empty-range",
        ),
        pytest.param(
            ("--category-name", "Rent", "--start", "2025-04"),
            datetime.date(2025, 4, 14),
            "Months to update: 2025-04",
            id="default-end-month",
        ),
    ],
)
@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.zero_out._get_category_id")
@patch("manager_for_ynab.zero_out._get_plan")
@patch("manager_for_ynab.zero_out.datetime.date")
def test_run_month_selection(
    date_cls,
    get_plan,
    get_category_id,
    capsys,
    ynab_configuration,
    ynab_api_client,
    ynab_plans_api,
    ynab_categories_api,
    argv,
    today,
    expected,
):
    date_cls.side_effect = REAL_DATE
    date_cls.today.return_value = today
    get_plan.return_value = ("plan-1", "Test Plan")
    get_category_id.return_value = ("cat-1", "Rent", "Fixed")
    ret = run(argv)

    out, _ = capsys.readouterr()
    assert ret == 0
    ynab_configuration.assert_called_once_with(access_token="token")
    ynab_api_client.assert_called_once_with(ynab_configuration.return_value)
    assert "Targeting Fixed - Rent from plan Test Plan" in out
    assert expected in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(asyncio, "run")
@patch(
    "manager_for_ynab.zero_out._get_plan",
    lambda plans_api, plan_id: ("plan-1", "Test Plan"),
)
def test_run_for_real_runs_updates(
    asyncio_run,
    ynab_configuration,
    ynab_api_client,
    ynab_plans_api,
    ynab_categories_api,
    category_group,
    categories_response,
):
    category_groups = [category_group("Fixed", ["Rent"])]
    ynab_categories_api.get_categories.return_value = categories_response(
        category_groups
    )

    captured: dict[str, Any] = {}

    def fake_asyncio_run(coro):
        captured["coroutine"] = coro
        coro.close()

    asyncio_run.side_effect = fake_asyncio_run

    ret = run(
        (
            "--category-name",
            "Rent",
            "--start",
            "2025-01",
            "--end",
            "2025-02",
            "--for-real",
        )
    )

    assert ret == 0
    ynab_configuration.assert_called_once_with(access_token="token")
    ynab_api_client.assert_called_once_with(ynab_configuration.return_value)
    assert captured["coroutine"].cr_code.co_name == "_run_updates"
