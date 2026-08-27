import json
from unittest.mock import MagicMock

import pytest

from manager_for_ynab._ynab_sync_api import delete_payee


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def raise_for_status(self):
        pass

    async def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_delete_payee_sends_tombstone_delta():
    fake_session = MagicMock()
    fake_session.post = MagicMock(
        return_value=_FakeResponse({"error": None, "current_server_knowledge": 7020})
    )

    result = await delete_payee(
        fake_session,
        cookie="cookie-value",
        session_token="token-value",
        budget_version_id="plan-1",
        payee_id="payee-1",
        payee_name="Amazon Duplicate",
        starting_device_knowledge=5,
        ending_device_knowledge=6,
        device_knowledge_of_server=7019,
    )

    assert result == {"error": None, "current_server_knowledge": 7020}
    fake_session.post.assert_called_once()

    _, kwargs = fake_session.post.call_args
    request_data = json.loads(kwargs["data"]["request_data"])
    assert request_data["budget_version_id"] == "plan-1"
    assert request_data["starting_device_knowledge"] == 5
    assert request_data["ending_device_knowledge"] == 6
    assert request_data["device_knowledge_of_server"] == 7019
    assert kwargs["headers"]["Cookie"] == "cookie-value"
    assert kwargs["headers"]["X-Session-Token"] == "token-value"

    payee_entity = request_data["changed_entities"]["be_payees"][0]
    assert payee_entity["id"] == "payee-1"
    assert payee_entity["is_tombstone"] is True
    assert payee_entity["name"] == "Amazon Duplicate"


@pytest.mark.asyncio
async def test_delete_payee_raises_on_error_response():
    fake_session = MagicMock()
    fake_session.post = MagicMock(
        return_value=_FakeResponse({"error": "not authorized"})
    )

    with pytest.raises(RuntimeError) as excinfo:
        await delete_payee(
            fake_session,
            cookie="cookie-value",
            session_token="token-value",
            budget_version_id="plan-1",
            payee_id="payee-1",
            payee_name="Amazon Duplicate",
            starting_device_knowledge=0,
            ending_device_knowledge=1,
            device_knowledge_of_server=0,
        )

    assert "not authorized" in str(excinfo.value)
