import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from ynab import CategoriesApi
from ynab import CategoriesResponse
from ynab import CategoriesResponseData
from ynab import Category
from ynab import CategoryGroupWithCategories
from ynab import PlansApi
from ynab import PlanSummary
from ynab import PlanSummaryResponse
from ynab import PlanSummaryResponseData

if TYPE_CHECKING:
    import datetime


@pytest.fixture
def plan_summary():
    def build(
        name: str,
        *,
        last_modified_on: datetime.datetime,
        plan_id: uuid.UUID | None = None,
    ) -> PlanSummary:
        return PlanSummary(
            id=plan_id or uuid.uuid4(), name=name, last_modified_on=last_modified_on
        )

    return build


@pytest.fixture
def plan_summary_response():
    def build(plans: list[PlanSummary]) -> PlanSummaryResponse:
        return PlanSummaryResponse(data=PlanSummaryResponseData(plans=plans))

    return build


@pytest.fixture
def category_group():
    def build(
        name: str, category_names: list[str], *, group_id: uuid.UUID | None = None
    ) -> CategoryGroupWithCategories:
        group_id = group_id or uuid.uuid4()
        return CategoryGroupWithCategories(
            id=group_id,
            name=name,
            hidden=False,
            deleted=False,
            categories=[
                Category(
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
        groups: list[CategoryGroupWithCategories],
    ) -> CategoriesResponse:
        return CategoriesResponse(
            data=CategoriesResponseData(category_groups=groups, server_knowledge=0)
        )

    return build


@pytest.fixture
def plans_api():
    return MagicMock(spec=PlansApi)


@pytest.fixture
def categories_api():
    return MagicMock(spec=CategoriesApi)


@pytest.fixture
def ynab_configuration():
    with patch("manager_for_ynab.zero_out.Configuration") as configuration:
        yield configuration


@pytest.fixture
def ynab_api_client():
    with patch("manager_for_ynab.zero_out.ApiClient") as api_client:
        yield api_client


@pytest.fixture
def ynab_plans_api():
    with patch("manager_for_ynab.zero_out.PlansApi") as plans_api_cls:
        yield plans_api_cls.return_value


@pytest.fixture
def ynab_categories_api():
    with patch("manager_for_ynab.zero_out.CategoriesApi") as categories_api_cls:
        yield categories_api_cls.return_value
