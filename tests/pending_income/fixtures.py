from unittest.mock import patch

import pytest

from manager_for_ynab.pending_income import ynab


@pytest.fixture
def ynab_configuration():
    with patch.object(ynab, "Configuration") as configuration:
        yield configuration


@pytest.fixture
def ynab_api_client():
    with patch.object(ynab, "ApiClient") as api_client:
        yield api_client


@pytest.fixture
def transactions_api():
    with patch.object(ynab, "TransactionsApi") as transactions_api_cls:
        yield transactions_api_cls.return_value
