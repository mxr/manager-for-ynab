import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import ynab

if TYPE_CHECKING:
    import datetime


@pytest.fixture
def plan_summary():
    def build(
        name: str,
        *,
        last_modified_on: datetime.datetime,
        plan_id: uuid.UUID | None = None,
    ) -> ynab.PlanSummary:
        return ynab.PlanSummary(
            id=plan_id or uuid.uuid4(), name=name, last_modified_on=last_modified_on
        )

    return build


@pytest.fixture
def plan_summary_response():
    def build(plans: list[ynab.PlanSummary]) -> ynab.PlanSummaryResponse:
        return ynab.PlanSummaryResponse(data=ynab.PlanSummaryResponseData(plans=plans))

    return build


@pytest.fixture
def category_group():
    def build(
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

    return build


@pytest.fixture
def categories_response():
    def build(
        groups: list[ynab.CategoryGroupWithCategories],
    ) -> ynab.CategoriesResponse:
        return ynab.CategoriesResponse(
            data=ynab.CategoriesResponseData(category_groups=groups, server_knowledge=0)
        )

    return build


@pytest.fixture
def plans_api():
    return MagicMock(spec=ynab.PlansApi)


@pytest.fixture
def categories_api():
    return MagicMock(spec=ynab.CategoriesApi)


@pytest.fixture
def ynab_configuration():
    with patch.object(ynab, "Configuration") as configuration:
        yield configuration


@pytest.fixture
def ynab_api_client():
    with patch.object(ynab, "ApiClient") as api_client:
        yield api_client


@pytest.fixture
def ynab_plans_api():
    with patch.object(ynab, "PlansApi") as plans_api_cls:
        yield plans_api_cls.return_value


@pytest.fixture
def ynab_categories_api():
    with patch.object(ynab, "CategoriesApi") as categories_api_cls:
        yield categories_api_cls.return_value
