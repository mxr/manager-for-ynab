import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from asyncio_for_ynab import CategoriesApi
from asyncio_for_ynab import CategoriesResponse
from asyncio_for_ynab import CategoriesResponseData
from asyncio_for_ynab import Category
from asyncio_for_ynab import CategoryGroupWithCategories
from asyncio_for_ynab import PlansApi
from asyncio_for_ynab import PlanSummary
from asyncio_for_ynab import PlanSummaryResponse
from asyncio_for_ynab import PlanSummaryResponseData

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
    return AsyncMock(spec=PlansApi)


@pytest.fixture
def categories_api():
    return AsyncMock(spec=CategoriesApi)


@pytest.fixture
def ynab_configuration():
    with patch("manager_for_ynab.zero_out.Configuration") as configuration:
        yield configuration


@pytest.fixture
def ynab_api_client():
    with patch("manager_for_ynab.zero_out.ApiClient") as api_client:
        api_client.return_value = AsyncMock()
        yield api_client


@pytest.fixture
def ynab_plans_api():
    with patch("manager_for_ynab.zero_out.PlansApi") as plans_api_cls:
        plans_api_cls.return_value = AsyncMock()
        yield plans_api_cls.return_value


@pytest.fixture
def ynab_categories_api():
    with patch("manager_for_ynab.zero_out.CategoriesApi") as categories_api_cls:
        categories_api_cls.return_value = AsyncMock()
        yield categories_api_cls.return_value
