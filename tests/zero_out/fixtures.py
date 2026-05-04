import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from unittest.mock import patch

import asyncio_for_ynab
import pytest

if TYPE_CHECKING:
    import datetime


@pytest.fixture
def plan_summary():
    def build(
        name: str,
        *,
        last_modified_on: datetime.datetime,
        plan_id: uuid.UUID | None = None,
    ) -> asyncio_for_ynab.PlanSummary:
        return asyncio_for_ynab.PlanSummary(
            id=plan_id or uuid.uuid4(), name=name, last_modified_on=last_modified_on
        )

    return build


@pytest.fixture
def plan_summary_response():
    def build(
        plans: list[asyncio_for_ynab.PlanSummary],
    ) -> asyncio_for_ynab.PlanSummaryResponse:
        return asyncio_for_ynab.PlanSummaryResponse(
            data=asyncio_for_ynab.PlanSummaryResponseData(plans=plans)
        )

    return build


@pytest.fixture
def category_group():
    def build(
        name: str, category_names: list[str], *, group_id: uuid.UUID | None = None
    ) -> asyncio_for_ynab.CategoryGroupWithCategories:
        group_id = group_id or uuid.uuid4()
        return asyncio_for_ynab.CategoryGroupWithCategories(
            id=group_id,
            name=name,
            hidden=False,
            deleted=False,
            categories=[
                asyncio_for_ynab.Category(
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
        groups: list[asyncio_for_ynab.CategoryGroupWithCategories],
    ) -> asyncio_for_ynab.CategoriesResponse:
        return asyncio_for_ynab.CategoriesResponse(
            data=asyncio_for_ynab.CategoriesResponseData(
                category_groups=groups, server_knowledge=0
            )
        )

    return build


@pytest.fixture
def plans_api():
    return AsyncMock(spec=asyncio_for_ynab.PlansApi)


@pytest.fixture
def categories_api():
    return AsyncMock(spec=asyncio_for_ynab.CategoriesApi)


@pytest.fixture
def ynab_configuration():
    with patch.object(asyncio_for_ynab, "Configuration") as configuration:
        yield configuration


@pytest.fixture
def ynab_api_client():
    with patch.object(asyncio_for_ynab, "ApiClient") as api_client:
        api_client.return_value = AsyncMock()
        yield api_client


@pytest.fixture
def ynab_plans_api():
    with patch.object(asyncio_for_ynab, "PlansApi") as plans_api_cls:
        plans_api_cls.return_value = AsyncMock()
        yield plans_api_cls.return_value


@pytest.fixture
def ynab_categories_api():
    with patch.object(asyncio_for_ynab, "CategoriesApi") as categories_api_cls:
        categories_api_cls.return_value = AsyncMock()
        yield categories_api_cls.return_value
