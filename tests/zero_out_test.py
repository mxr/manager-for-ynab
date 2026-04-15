import argparse
import datetime
from types import SimpleNamespace
from typing import Any

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

    run_updates_called = False

    def fake_run_updates(*args, **kwargs):
        nonlocal run_updates_called
        run_updates_called = True

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
    assert run_updates_called is False


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
