import argparse
import asyncio
import datetime
import uuid
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


def make_plan(
    name: str, *, last_modified_on: datetime.datetime, plan_id: uuid.UUID | None = None
) -> ynab.PlanSummary:
    return ynab.PlanSummary(
        id=plan_id or uuid.uuid4(), name=name, last_modified_on=last_modified_on
    )


def make_plans_response(plans: list[ynab.PlanSummary]) -> ynab.PlanSummaryResponse:
    return ynab.PlanSummaryResponse(data=ynab.PlanSummaryResponseData(plans=plans))


def make_category_group(
    name: str, category_names: list[str], *, group_id: uuid.UUID | None = None
) -> ynab.CategoryGroupWithCategories:
    group_id = group_id or uuid.uuid4()
    return ynab.CategoryGroupWithCategories(
        id=group_id,
        name=name,
        hidden=False,
        deleted=False,
        categories=[
            ynab.Category(
                id=uuid.uuid4(),
                category_group_id=group_id,
                category_group_name=name,
                name=category_name,
                hidden=False,
                budgeted=0,
                activity=0,
                balance=0,
                deleted=False,
            )
            for category_name in category_names
        ],
    )


def make_categories_response(
    groups: list[ynab.CategoryGroupWithCategories],
) -> ynab.CategoriesResponse:
    return ynab.CategoriesResponse(
        data=ynab.CategoriesResponseData(category_groups=groups, server_knowledge=0)
    )


class FakePlansApi:
    def __init__(
        self,
        *,
        response: ynab.PlanSummaryResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error

    def get_plans(self) -> ynab.PlanSummaryResponse:
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class FakeCategoriesApi:
    def __init__(
        self,
        *,
        response: ynab.CategoriesResponse | None = None,
        get_error: Exception | None = None,
        update_error: Exception | None = None,
    ) -> None:
        self.response = response
        self.get_error = get_error
        self.update_error = update_error
        self.updates: list[tuple[str, object, str, object]] = []

    def get_categories(self, plan_id: str) -> ynab.CategoriesResponse:
        if self.get_error is not None:
            raise self.get_error
        assert self.response is not None
        return self.response

    def update_month_category(
        self, plan_id: str, month: object, category_id: str, data: object
    ) -> None:
        if self.update_error is not None:
            raise self.update_error
        self.updates.append((plan_id, month, category_id, data))


class FakeConfiguration:
    def __init__(self, access_token: str) -> None:
        self.access_token = access_token


class FakeApiClient:
    def __init__(self, configuration: FakeConfiguration) -> None:
        self.configuration = configuration

    def __enter__(self) -> FakeApiClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> Literal[False]:
        return False


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


def test_get_plan_uses_latest_plan():
    response = make_plans_response(
        [
            make_plan("Old", last_modified_on=datetime.datetime(2025, 1, 1)),
            make_plan("New", last_modified_on=datetime.datetime(2025, 2, 1)),
        ]
    )
    plans_api = FakePlansApi(response=response)

    assert _get_plan(cast("Any", plans_api), None) == (
        str(response.data.plans[1].id),
        "New",
    )


def test_get_plan_uses_explicit_plan_id():
    plan = make_plan("Chosen", last_modified_on=datetime.datetime(2025, 2, 1))
    plans_api = FakePlansApi(response=make_plans_response([plan]))

    assert _get_plan(cast("Any", plans_api), str(plan.id)) == (
        str(plan.id),
        "Chosen",
    )


def test_get_plan_errors_when_explicit_plan_id_is_missing():
    plans_api = FakePlansApi(
        response=make_plans_response(
            [make_plan("Other", last_modified_on=datetime.datetime(2025, 2, 1))]
        )
    )

    with pytest.raises(RuntimeError) as excinfo:
        _get_plan(cast("Any", plans_api), "plan-123")

    assert str(excinfo.value) == "No plan found with id 'plan-123'."


@pytest.mark.parametrize(
    ("plans_api", "expected_message"),
    [
        pytest.param(
            FakePlansApi(error=ynab.ApiException(status=500, reason="boom")),
            "Failed to fetch plans",
            id="api-error",
        ),
        pytest.param(
            FakePlansApi(response=make_plans_response([])),
            "No plans found",
            id="empty-list",
        ),
    ],
)
def test_get_plan_errors(plans_api, expected_message):
    with pytest.raises(RuntimeError) as excinfo:
        _get_plan(cast("Any", plans_api), None)

    assert expected_message in str(excinfo.value)


@pytest.mark.parametrize(
    ("category_group", "category_name", "groups", "expected"),
    [
        pytest.param(
            None,
            "Rent",
            [make_category_group("Fixed", ["Rent"])],
            ("Rent", "Fixed"),
            id="substring-name-without-group",
        ),
        pytest.param(
            "Vari",
            "rent",
            [
                make_category_group("Fixed", ["Rent"]),
                make_category_group("Variable", ["Rent"]),
            ],
            ("Rent", "Variable"),
            id="substring-group-and-name",
        ),
        pytest.param(
            "^Var",
            r"Ren.",
            [
                make_category_group("Fixed", ["Rent"]),
                make_category_group("Variable", ["Rent"]),
            ],
            ("Rent", "Variable"),
            id="explicit-regex-patterns",
        ),
    ],
)
def test_get_category_id_matches_plan_categories(
    category_group, category_name, groups, expected
):
    categories_api = FakeCategoriesApi(response=make_categories_response(groups))

    category_id, matched_name, matched_group = _get_category_id(
        cast("Any", categories_api), "plan-1", category_group, category_name
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
    ("category_group", "category_name", "groups", "expected_message"),
    [
        pytest.param(
            None,
            "Rent",
            [
                make_category_group("Fixed", ["Rent"]),
                make_category_group("Variable", ["Rent"]),
            ],
            "Found 2 categories matching regex 'Rent'",
            id="ambiguous-name",
        ),
        pytest.param(
            "Fixed",
            "Rent",
            [make_category_group("Fixed", ["Rent", "Rent 2"])],
            "Found 2 categories matching regex 'Rent' in group matching regex 'Fixed'",
            id="ambiguous-regex-in-group",
        ),
        pytest.param(
            "Variable",
            "Rent",
            [make_category_group("Fixed", ["Rent"])],
            "No category matching regex 'Rent' found in group matching regex 'Variable'.",
            id="missing-in-group",
        ),
        pytest.param(
            None,
            "Groceries",
            [make_category_group("Fixed", ["Rent"])],
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
    category_group, category_name, groups, expected_message
):
    categories_api = FakeCategoriesApi(response=make_categories_response(groups))

    with pytest.raises(RuntimeError) as excinfo:
        _get_category_id(
            cast("Any", categories_api), "plan-1", category_group, category_name
        )

    assert expected_message in str(excinfo.value)


def test_get_category_id_wraps_api_exception():
    categories_api = FakeCategoriesApi(
        get_error=ynab.ApiException(status=500, reason="boom")
    )

    with pytest.raises(RuntimeError) as excinfo:
        _get_category_id(cast("Any", categories_api), "plan-1", None, "rent")

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
def test_update_month_category(update_error, expected):
    categories_api = FakeCategoriesApi(update_error=update_error)

    month_str, error = _update_month_category(
        cast("Any", categories_api), "plan-1", "cat-1", 2025, 2
    )

    assert month_str == expected[0]
    if expected[1] is None:
        assert error is None
        assert categories_api.updates[0][0] == "plan-1"
        assert categories_api.updates[0][2] == "cat-1"
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


@patch.dict("os.environ", {}, clear=True)
@patch("manager_for_ynab.zero_out._run_updates")
@patch.object(ynab, "CategoriesApi")
@patch.object(ynab, "PlansApi")
@patch.object(ynab, "ApiClient", FakeApiClient)
@patch.object(ynab, "Configuration")
def test_run_uses_token_override(
    configuration, plans_api_cls, categories_api_cls, run_updates, capsys
):
    captured: dict[str, str] = {}
    plans = [make_plan("New", last_modified_on=datetime.datetime(2025, 2, 1))]
    category_groups = [make_category_group("Fixed", ["Rent"])]

    def fake_configuration(access_token: str) -> FakeConfiguration:
        captured["token"] = access_token
        return FakeConfiguration(access_token)

    configuration.side_effect = fake_configuration
    plans_api_cls.side_effect = lambda client: FakePlansApi(
        response=make_plans_response(plans)
    )
    categories_api_cls.side_effect = lambda client: FakeCategoriesApi(
        response=make_categories_response(category_groups)
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
    assert captured["token"] == "override-token"
    assert "Targeting Fixed - Rent from plan New" in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.zero_out._run_updates")
@patch.object(ynab, "CategoriesApi")
@patch.object(ynab, "PlansApi")
@patch.object(ynab, "ApiClient", FakeApiClient)
@patch.object(ynab, "Configuration", FakeConfiguration)
def test_run_dry_run_prints_preview(
    plans_api_cls, categories_api_cls, run_updates, capsys
):
    plans = [make_plan("New", last_modified_on=datetime.datetime(2025, 2, 1))]
    category_groups = [make_category_group("Fixed", ["Rent"])]
    plans_api_cls.side_effect = lambda client: FakePlansApi(
        response=make_plans_response(plans)
    )
    categories_api_cls.side_effect = lambda client: FakeCategoriesApi(
        response=make_categories_response(category_groups)
    )
    run_updates.side_effect = AssertionError(
        "_run_updates should not run during dry-run"
    )

    ret = run(("--category-name", "Rent", "--start", "2025-01", "--end", "2025-02"))

    out, _ = capsys.readouterr()
    assert ret == 0
    assert "Targeting Fixed - Rent from plan New" in out
    assert "Months to update: 2025-01, 2025-02" in out
    assert "Use --for-real to actually update categories." in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch("manager_for_ynab.zero_out._get_plan")
@patch.object(ynab, "CategoriesApi", lambda client: cast("Any", object()))
@patch.object(ynab, "PlansApi", lambda client: cast("Any", object()))
@patch.object(ynab, "ApiClient", FakeApiClient)
@patch.object(ynab, "Configuration", FakeConfiguration)
def test_run_returns_error_when_plan_lookup_fails(get_plan, capsys):
    get_plan.side_effect = RuntimeError("bad plan")

    ret = run(("--category-name", "Rent", "--start", "2025-01"))

    out, _ = capsys.readouterr()
    assert ret == 1
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
@patch.object(ynab, "CategoriesApi", lambda client: cast("Any", object()))
@patch.object(ynab, "PlansApi", lambda client: cast("Any", object()))
@patch.object(ynab, "ApiClient", FakeApiClient)
@patch.object(ynab, "Configuration", FakeConfiguration)
def test_run_month_selection(
    date_cls, get_plan, get_category_id, capsys, argv, today, expected
):
    date_cls.side_effect = REAL_DATE
    date_cls.today.return_value = today
    get_plan.return_value = ("plan-1", "Test Plan")
    get_category_id.return_value = ("cat-1", "Rent", "Fixed")
    ret = run(argv)

    out, _ = capsys.readouterr()
    assert ret == 0
    assert "Targeting Fixed - Rent from plan Test Plan" in out
    assert expected in out


@patch.dict("os.environ", {_ENV_TOKEN: "token"})
@patch.object(asyncio, "run")
@patch.object(ynab, "CategoriesApi")
@patch.object(ynab, "PlansApi", lambda client: cast("Any", object()))
@patch.object(ynab, "ApiClient", FakeApiClient)
@patch.object(ynab, "Configuration", FakeConfiguration)
@patch(
    "manager_for_ynab.zero_out._get_plan",
    lambda plans_api, plan_id: ("plan-1", "Test Plan"),
)
def test_run_for_real_runs_updates(categories_api_cls, asyncio_run):
    category_groups = [make_category_group("Fixed", ["Rent"])]
    categories_api_cls.side_effect = lambda client: FakeCategoriesApi(
        response=make_categories_response(category_groups)
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
    assert captured["coroutine"].cr_code.co_name == "_run_updates"
