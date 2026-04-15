import argparse
import asyncio
import datetime
from types import SimpleNamespace
from typing import Any
from typing import cast

import pytest

from manager_for_ynab import zero_out


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


def test_get_plan_id_uses_latest_plan():
    plans = [
        SimpleNamespace(
            id="plan-1", name="Old", last_modified_on=datetime.datetime(2025, 1, 1)
        ),
        SimpleNamespace(
            id="plan-2", name="New", last_modified_on=datetime.datetime(2025, 2, 1)
        ),
    ]
    plans_api = SimpleNamespace(
        get_plans=lambda: SimpleNamespace(data=SimpleNamespace(plans=plans))
    )

    assert zero_out._get_plan_id(plans_api, None) == "plan-2"  # type: ignore[arg-type]


def test_get_plan_id_uses_explicit_plan_id():
    assert zero_out._get_plan_id(SimpleNamespace(), "plan-123") == "plan-123"  # type: ignore[arg-type]


def test_get_plan_id_wraps_api_exception():
    class FakePlansApi:
        def get_plans(self):
            raise zero_out.ynab.ApiException(status=500, reason="boom")

    with pytest.raises(RuntimeError) as excinfo:
        zero_out._get_plan_id(FakePlansApi(), None)  # type: ignore[arg-type]

    assert "Failed to fetch plans" in str(excinfo.value)


def test_get_plan_id_rejects_empty_plan_list():
    plans_api = SimpleNamespace(
        get_plans=lambda: SimpleNamespace(data=SimpleNamespace(plans=[]))
    )

    with pytest.raises(RuntimeError) as excinfo:
        zero_out._get_plan_id(plans_api, None)  # type: ignore[arg-type]

    assert "No plans found" in str(excinfo.value)


def test_get_category_id_requires_unique_match():
    categories_api = SimpleNamespace(
        get_categories=lambda plan_id: SimpleNamespace(
            data=SimpleNamespace(
                category_groups=[
                    SimpleNamespace(
                        categories=[
                            SimpleNamespace(id="cat-1", name="Rent"),
                            SimpleNamespace(id="cat-2", name="Renters"),
                        ]
                    )
                ]
            )
        )
    )

    with pytest.raises(RuntimeError) as excinfo:
        zero_out._get_category_id(categories_api, "plan-1", "rent")  # type: ignore[arg-type]

    assert "Found 2 categories" in str(excinfo.value)


def test_get_category_id_wraps_api_exception():
    class FakeCategoriesApi:
        def get_categories(self, plan_id):
            raise zero_out.ynab.ApiException(status=500, reason="boom")

    with pytest.raises(RuntimeError) as excinfo:
        zero_out._get_category_id(FakeCategoriesApi(), "plan-1", "rent")  # type: ignore[arg-type]

    assert "Failed to fetch categories" in str(excinfo.value)


def test_update_month_category_success():
    updates: list[tuple[str, object, str, object]] = []

    class FakeCategoriesApi:
        def update_month_category(self, plan_id, month, category_id, data):
            updates.append((plan_id, month, category_id, data))

    assert zero_out._update_month_category(
        cast("Any", FakeCategoriesApi()), "plan-1", "cat-1", 2025, 2
    ) == ("2025-02", None)
    assert updates[0][0] == "plan-1"
    assert updates[0][2] == "cat-1"


def test_update_month_category_returns_error_message():
    class FakeCategoriesApi:
        def update_month_category(self, plan_id, month, category_id, data):
            raise zero_out.ynab.ApiException(status=400, reason="bad request")

    month_str, error = zero_out._update_month_category(
        cast("Any", FakeCategoriesApi()), "plan-1", "cat-1", 2025, 2
    )
    assert month_str == "2025-02"
    assert error is not None


@pytest.mark.asyncio
async def test_run_updates_prints_success_and_failure(monkeypatch, capsys):
    class FakeExecutor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
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
        cast("Any", SimpleNamespace()), "plan-1", "cat-1", ((2025, 1), (2025, 2))
    )

    out, _ = capsys.readouterr()
    assert "2025-01: set planned to 0." in out
    assert "Failed to update month 2025-02: boom" in out


def test_main_requires_token(monkeypatch):
    monkeypatch.setenv(zero_out._ENV_TOKEN, "")

    with pytest.raises(ValueError) as excinfo:
        zero_out.main(("--category-name", "Rent", "--start", "2025-01"))

    assert "Must set YNAB access token" in str(excinfo.value)


def test_main_dry_run_prints_preview(monkeypatch, capsys):
    monkeypatch.setenv(zero_out._ENV_TOKEN, "token")

    class FakeApiClient:
        def __init__(self, configuration):
            self.configuration = configuration

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    plans = [
        SimpleNamespace(
            id="plan-2", name="New", last_modified_on=datetime.datetime(2025, 2, 1)
        )
    ]
    categories = [SimpleNamespace(id="cat-1", name="Rent")]

    monkeypatch.setattr(
        zero_out.ynab,
        "Configuration",
        lambda access_token: SimpleNamespace(access_token=access_token),
    )
    monkeypatch.setattr(zero_out.ynab, "ApiClient", FakeApiClient)
    monkeypatch.setattr(
        zero_out.ynab,
        "PlansApi",
        lambda client: SimpleNamespace(
            get_plans=lambda: SimpleNamespace(data=SimpleNamespace(plans=plans))
        ),
    )
    monkeypatch.setattr(
        zero_out.ynab,
        "CategoriesApi",
        lambda client: SimpleNamespace(
            get_categories=lambda plan_id: SimpleNamespace(
                data=SimpleNamespace(
                    category_groups=[SimpleNamespace(categories=categories)]
                )
            )
        ),
    )

    def fake_run_updates(*args, **kwargs):
        raise AssertionError("_run_updates should not run during dry-run")

    monkeypatch.setattr(zero_out, "_run_updates", fake_run_updates)

    ret = zero_out.main(
        ("--category-name", "Rent", "--start", "2025-01", "--end", "2025-02")
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    assert "Using plan: New (plan-2)" in out
    assert "Using category: Rent (cat-1)" in out
    assert "Months to update: 2025-01, 2025-02" in out
    assert "Use --for-real to actually update categories." in out


def test_main_returns_error_when_plan_lookup_fails(monkeypatch, capsys):
    monkeypatch.setenv(zero_out._ENV_TOKEN, "token")

    class FakeApiClient:
        def __init__(self, configuration):
            self.configuration = configuration

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        zero_out.ynab,
        "Configuration",
        lambda access_token: SimpleNamespace(access_token=access_token),
    )
    monkeypatch.setattr(zero_out.ynab, "ApiClient", FakeApiClient)
    monkeypatch.setattr(zero_out.ynab, "PlansApi", lambda client: SimpleNamespace())
    monkeypatch.setattr(
        zero_out.ynab, "CategoriesApi", lambda client: SimpleNamespace()
    )
    monkeypatch.setattr(
        zero_out,
        "_get_plan_id",
        lambda plans_api, plan_id: (_ for _ in ()).throw(RuntimeError("bad plan")),
    )

    ret = zero_out.main(("--category-name", "Rent", "--start", "2025-01"))

    out, _ = capsys.readouterr()
    assert ret == 1
    assert "bad plan" in out


def test_main_returns_zero_when_month_range_is_empty(monkeypatch, capsys):
    monkeypatch.setenv(zero_out._ENV_TOKEN, "token")

    class FakeApiClient:
        def __init__(self, configuration):
            self.configuration = configuration

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        zero_out.ynab,
        "Configuration",
        lambda access_token: SimpleNamespace(access_token=access_token),
    )
    monkeypatch.setattr(zero_out.ynab, "ApiClient", FakeApiClient)
    monkeypatch.setattr(zero_out.ynab, "PlansApi", lambda client: SimpleNamespace())
    monkeypatch.setattr(
        zero_out.ynab, "CategoriesApi", lambda client: SimpleNamespace()
    )
    monkeypatch.setattr(zero_out, "_get_plan_id", lambda plans_api, plan_id: "plan-1")
    monkeypatch.setattr(
        zero_out,
        "_get_category_id",
        lambda categories_api, plan_id, category_name: ("cat-1", "Rent"),
    )

    ret = zero_out.main(
        ("--category-name", "Rent", "--start", "2025-03", "--end", "2025-02")
    )

    out, _ = capsys.readouterr()
    assert ret == 0
    assert "No months selected." in out


def test_main_uses_current_month_when_end_omitted(monkeypatch, capsys):
    monkeypatch.setenv(zero_out._ENV_TOKEN, "token")

    class FakeApiClient:
        def __init__(self, configuration):
            self.configuration = configuration

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2025, 4, 14)

    monkeypatch.setattr(
        zero_out.ynab,
        "Configuration",
        lambda access_token: SimpleNamespace(access_token=access_token),
    )
    monkeypatch.setattr(zero_out.ynab, "ApiClient", FakeApiClient)
    monkeypatch.setattr(zero_out.ynab, "PlansApi", lambda client: SimpleNamespace())
    monkeypatch.setattr(
        zero_out.ynab, "CategoriesApi", lambda client: SimpleNamespace()
    )
    monkeypatch.setattr(zero_out, "_get_plan_id", lambda plans_api, plan_id: "plan-1")
    monkeypatch.setattr(
        zero_out,
        "_get_category_id",
        lambda categories_api, plan_id, category_name: ("cat-1", "Rent"),
    )
    monkeypatch.setattr(zero_out.datetime, "date", FakeDate)

    ret = zero_out.main(("--category-name", "Rent", "--start", "2025-04"))

    out, _ = capsys.readouterr()
    assert ret == 0
    assert "Months to update: 2025-04" in out


def test_main_for_real_runs_updates(monkeypatch):
    monkeypatch.setenv(zero_out._ENV_TOKEN, "token")

    class FakeApiClient:
        def __init__(self, configuration):
            self.configuration = configuration

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    plans_api = SimpleNamespace(
        get_plans=lambda: SimpleNamespace(data=SimpleNamespace(plans=[]))
    )
    categories_api = SimpleNamespace(
        get_categories=lambda plan_id: SimpleNamespace(
            data=SimpleNamespace(
                category_groups=[
                    SimpleNamespace(
                        categories=[SimpleNamespace(id="cat-1", name="Rent")]
                    )
                ]
            )
        )
    )

    monkeypatch.setattr(
        zero_out.ynab,
        "Configuration",
        lambda access_token: SimpleNamespace(access_token=access_token),
    )
    monkeypatch.setattr(zero_out.ynab, "ApiClient", FakeApiClient)
    monkeypatch.setattr(zero_out.ynab, "PlansApi", lambda client: plans_api)
    monkeypatch.setattr(zero_out.ynab, "CategoriesApi", lambda client: categories_api)
    monkeypatch.setattr(zero_out, "_get_plan_id", lambda plans_api, plan_id: "plan-1")

    captured: dict[str, Any] = {}

    def fake_asyncio_run(coro):
        captured["coroutine"] = coro
        coro.close()

    monkeypatch.setattr(zero_out.asyncio, "run", fake_asyncio_run)

    ret = zero_out.main(
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
