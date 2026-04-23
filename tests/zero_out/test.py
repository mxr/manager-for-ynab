import argparse
import asyncio
import datetime
import uuid
from typing import Any
from typing import cast
from typing import Literal

import pytest
import ynab

import manager_for_ynab.zero_out as zero_out
from manager_for_ynab._auth import _ENV_TOKEN


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


def install_run_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    plans: list[ynab.PlanSummary] | None = None,
    category_groups: list[ynab.CategoryGroupWithCategories] | None = None,
) -> None:
    monkeypatch.setattr(zero_out.ynab, "Configuration", FakeConfiguration)
    monkeypatch.setattr(zero_out.ynab, "ApiClient", FakeApiClient)
    monkeypatch.setattr(
        zero_out.ynab,
        "PlansApi",
        lambda client: FakePlansApi(response=make_plans_response(plans or [])),
    )
    monkeypatch.setattr(
        zero_out.ynab,
        "CategoriesApi",
        lambda client: FakeCategoriesApi(
            response=make_categories_response(category_groups or [])
        ),
    )


def test_month_range_is_inclusive():
    assert tuple(zero_out.month_range(2025, 11, 2026, 2)) == (
        (2025, 11),
        (2025, 12),
        (2026, 1),
        (2026, 2),
    )


def test_parse_year_month_rejects_invalid_month():
    with pytest.raises(argparse.ArgumentTypeError):
        zero_out.parse_year_month("2025-13")


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        pytest.param("Rent", "%Rent%", id="wraps-plain-text"),
        pytest.param("%Rent", "%Rent", id="preserves-percent"),
        pytest.param("Rent_", "Rent_", id="preserves-underscore"),
    ],
)
def test_normalize_like_pattern(pattern, expected):
    assert zero_out._normalize_like_pattern(pattern) == expected


@pytest.mark.parametrize(
    ("value", "pattern", "expected"),
    [
        pytest.param("Medical", "med", True, id="implicit-substring"),
        pytest.param("True Expenses", "true%", True, id="explicit-percent"),
        pytest.param("Rent 2", "Rent _", True, id="explicit-underscore"),
        pytest.param("Rent 20", "Rent _", False, id="underscore-is-single-char"),
    ],
)
def test_like_match(value, pattern, expected):
    assert zero_out._like_match(value, pattern) is expected


def test_get_plan_uses_latest_plan():
    response = make_plans_response(
        [
            make_plan("Old", last_modified_on=datetime.datetime(2025, 1, 1)),
            make_plan("New", last_modified_on=datetime.datetime(2025, 2, 1)),
        ]
    )
    plans_api = FakePlansApi(response=response)

    assert zero_out._get_plan(cast("Any", plans_api), None) == (
        str(response.data.plans[1].id),
        "New",
    )


def test_get_plan_uses_explicit_plan_id():
    plan = make_plan("Chosen", last_modified_on=datetime.datetime(2025, 2, 1))
    plans_api = FakePlansApi(response=make_plans_response([plan]))

    assert zero_out._get_plan(cast("Any", plans_api), str(plan.id)) == (
        str(plan.id),
        "Chosen",
    )


def test_get_plan_falls_back_to_plan_id_when_explicit_plan_name_is_missing():
    plans_api = FakePlansApi(
        response=make_plans_response(
            [make_plan("Other", last_modified_on=datetime.datetime(2025, 2, 1))]
        )
    )

    assert zero_out._get_plan(cast("Any", plans_api), "plan-123") == (
        "plan-123",
        "plan-123",
    )


@pytest.mark.parametrize(
    ("plans_api", "expected_message"),
    [
        pytest.param(
            FakePlansApi(error=zero_out.ynab.ApiException(status=500, reason="boom")),
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
        zero_out._get_plan(cast("Any", plans_api), None)

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
            "Var%",
            "Ren_",
            [
                make_category_group("Fixed", ["Rent"]),
                make_category_group("Variable", ["Rent"]),
            ],
            ("Rent", "Variable"),
            id="explicit-like-patterns",
        ),
    ],
)
def test_get_category_id_matches_plan_categories(
    category_group, category_name, groups, expected
):
    categories_api = FakeCategoriesApi(response=make_categories_response(groups))

    category_id, matched_name, matched_group = zero_out._get_category_id(
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
            "Found 2 categories matching LIKE '%Rent%'",
            id="ambiguous-name",
        ),
        pytest.param(
            "Fixed",
            "Rent",
            [make_category_group("Fixed", ["Rent", "Rent 2"])],
            "Found 2 categories matching LIKE '%Rent%' in group matching LIKE '%Fixed%'",
            id="ambiguous-substring-in-group",
        ),
        pytest.param(
            "Variable",
            "Rent",
            [make_category_group("Fixed", ["Rent"])],
            "No category matching LIKE '%Rent%' found in group matching LIKE '%Variable%'.",
            id="missing-in-group",
        ),
        pytest.param(
            None,
            "Groceries",
            [make_category_group("Fixed", ["Rent"])],
            "No category matching LIKE '%Groceries%' found in this plan.",
            id="missing-in-plan",
        ),
        pytest.param(
            None,
            "Rent",
            [],
            "No category matching LIKE '%Rent%' found in this plan.",
            id="missing-in-empty-plan",
        ),
    ],
)
def test_get_category_id_errors(
    category_group, category_name, groups, expected_message
):
    categories_api = FakeCategoriesApi(response=make_categories_response(groups))

    with pytest.raises(RuntimeError) as excinfo:
        zero_out._get_category_id(
            cast("Any", categories_api), "plan-1", category_group, category_name
        )

    assert expected_message in str(excinfo.value)


def test_get_category_id_wraps_api_exception():
    categories_api = FakeCategoriesApi(
        get_error=zero_out.ynab.ApiException(status=500, reason="boom")
    )

    with pytest.raises(RuntimeError) as excinfo:
        zero_out._get_category_id(cast("Any", categories_api), "plan-1", None, "rent")

    assert "Failed to fetch categories" in str(excinfo.value)


@pytest.mark.parametrize(
    ("update_error", "expected"),
    [
        pytest.param(None, ("2025-02", None), id="success"),
        pytest.param(
            zero_out.ynab.ApiException(status=400, reason="bad request"),
            ("2025-02", "error"),
            id="api-error",
        ),
    ],
)
def test_update_month_category(update_error, expected):
    categories_api = FakeCategoriesApi(update_error=update_error)

    month_str, error = zero_out._update_month_category(
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
async def test_run_updates_prints_success_and_failure(monkeypatch, capsys):
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
    monkeypatch.setattr(
        zero_out, "ThreadPoolExecutor", lambda max_workers: FakeExecutor()
    )
    monkeypatch.setattr(zero_out.asyncio, "get_running_loop", lambda: fake_loop)

    await zero_out._run_updates(
        cast("Any", object()), "plan-1", "cat-1", ((2025, 1), (2025, 2))
    )

    out, _ = capsys.readouterr()
    assert "2025-01: set planned to 0." in out
    assert "Failed to update month 2025-02: boom" in out


def test_run_requires_token(monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, "")

    with pytest.raises(ValueError) as excinfo:
        zero_out.run(("--category-name", "Rent", "--start", "2025-01"))

    assert "Must set YNAB access token" in str(excinfo.value)


def test_run_uses_token_override(monkeypatch, capsys):
    monkeypatch.delenv(_ENV_TOKEN, raising=False)
    captured: dict[str, str] = {}
    plans = [make_plan("New", last_modified_on=datetime.datetime(2025, 2, 1))]
    category_groups = [make_category_group("Fixed", ["Rent"])]

    def fake_configuration(access_token: str) -> FakeConfiguration:
        captured["token"] = access_token
        return FakeConfiguration(access_token)

    monkeypatch.setattr(zero_out.ynab, "Configuration", fake_configuration)
    monkeypatch.setattr(zero_out.ynab, "ApiClient", FakeApiClient)
    monkeypatch.setattr(
        zero_out.ynab,
        "PlansApi",
        lambda client: FakePlansApi(response=make_plans_response(plans)),
    )
    monkeypatch.setattr(
        zero_out.ynab,
        "CategoriesApi",
        lambda client: FakeCategoriesApi(
            response=make_categories_response(category_groups)
        ),
    )
    monkeypatch.setattr(
        zero_out,
        "_run_updates",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("_run_updates should not run during dry-run")
        ),
    )

    ret = zero_out.run(
        ("--category-name", "Rent", "--start", "2025-01", "--end", "2025-02"),
        token_override="override-token",
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    assert captured["token"] == "override-token"
    assert "Targeting Fixed - Rent from plan New" in out


def test_run_dry_run_prints_preview(monkeypatch, capsys):
    monkeypatch.setenv(_ENV_TOKEN, "token")
    plans = [make_plan("New", last_modified_on=datetime.datetime(2025, 2, 1))]
    category_groups = [make_category_group("Fixed", ["Rent"])]

    install_run_dependencies(monkeypatch, plans=plans, category_groups=category_groups)

    def fake_run_updates(*args, **kwargs):
        raise AssertionError("_run_updates should not run during dry-run")

    monkeypatch.setattr(zero_out, "_run_updates", fake_run_updates)

    ret = zero_out.run(
        ("--category-name", "Rent", "--start", "2025-01", "--end", "2025-02")
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    assert "Targeting Fixed - Rent from plan New" in out
    assert "Months to update: 2025-01, 2025-02" in out
    assert "Use --for-real to actually update categories." in out


def test_run_returns_error_when_plan_lookup_fails(monkeypatch, capsys):
    monkeypatch.setenv(_ENV_TOKEN, "token")

    monkeypatch.setattr(zero_out.ynab, "Configuration", FakeConfiguration)
    monkeypatch.setattr(zero_out.ynab, "ApiClient", FakeApiClient)
    monkeypatch.setattr(zero_out.ynab, "PlansApi", lambda client: cast("Any", object()))
    monkeypatch.setattr(
        zero_out.ynab, "CategoriesApi", lambda client: cast("Any", object())
    )
    monkeypatch.setattr(
        zero_out,
        "_get_plan",
        lambda plans_api, plan_id: (_ for _ in ()).throw(RuntimeError("bad plan")),
    )

    ret = zero_out.run(("--category-name", "Rent", "--start", "2025-01"))

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
def test_run_month_selection(monkeypatch, capsys, argv, today, expected):
    monkeypatch.setenv(_ENV_TOKEN, "token")

    class FakeDate(datetime.date):
        @classmethod
        def today(cls):
            assert today is not None
            return cls(today.year, today.month, today.day)

    monkeypatch.setattr(zero_out.ynab, "Configuration", FakeConfiguration)
    monkeypatch.setattr(zero_out.ynab, "ApiClient", FakeApiClient)
    monkeypatch.setattr(zero_out.ynab, "PlansApi", lambda client: cast("Any", object()))
    monkeypatch.setattr(
        zero_out.ynab, "CategoriesApi", lambda client: cast("Any", object())
    )
    monkeypatch.setattr(
        zero_out, "_get_plan", lambda plans_api, plan_id: ("plan-1", "Test Plan")
    )
    monkeypatch.setattr(
        zero_out,
        "_get_category_id",
        lambda categories_api, plan_id, category_group, category_name: (
            "cat-1",
            "Rent",
            "Fixed",
        ),
    )
    if today is not None:
        monkeypatch.setattr(zero_out.datetime, "date", FakeDate)

    ret = zero_out.run(argv)

    out, _ = capsys.readouterr()
    assert ret == 0
    assert "Targeting Fixed - Rent from plan Test Plan" in out
    assert expected in out


def test_run_for_real_runs_updates(monkeypatch):
    monkeypatch.setenv(_ENV_TOKEN, "token")
    category_groups = [make_category_group("Fixed", ["Rent"])]

    monkeypatch.setattr(zero_out.ynab, "Configuration", FakeConfiguration)
    monkeypatch.setattr(zero_out.ynab, "ApiClient", FakeApiClient)
    monkeypatch.setattr(zero_out.ynab, "PlansApi", lambda client: cast("Any", object()))
    monkeypatch.setattr(
        zero_out.ynab,
        "CategoriesApi",
        lambda client: FakeCategoriesApi(
            response=make_categories_response(category_groups)
        ),
    )
    monkeypatch.setattr(
        zero_out, "_get_plan", lambda plans_api, plan_id: ("plan-1", "Test Plan")
    )

    captured: dict[str, Any] = {}

    def fake_asyncio_run(coro):
        captured["coroutine"] = coro
        coro.close()

    monkeypatch.setattr(zero_out.asyncio, "run", fake_asyncio_run)

    ret = zero_out.run(
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
