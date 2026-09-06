import json
import uuid
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    import aiohttp

_SYNC_URL = "https://app.ynab.com/api/v1/catalog"
_API_VERSION = "2026-01-01"
_SCHEMA_VERSION = 44


async def _sync_budget_data(
    session: aiohttp.ClientSession,
    *,
    cookie: str,
    session_token: str,
    budget_version_id: str,
    starting_device_knowledge: int,
    ending_device_knowledge: int,
    device_knowledge_of_server: int,
    changed_entities: dict[str, Any],
) -> dict[str, Any]:
    request_data = {
        "budget_version_id": budget_version_id,
        "sync_type": "delta",
        "starting_device_knowledge": starting_device_knowledge,
        "ending_device_knowledge": ending_device_knowledge,
        "device_knowledge_of_server": device_knowledge_of_server,
        "calculated_entities_included": False,
        "schema_version": _SCHEMA_VERSION,
        "schema_version_of_knowledge": _SCHEMA_VERSION,
        "changed_entities": changed_entities,
    }
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "X-YNAB-Client-Request-Id": str(uuid.uuid4()),
        "X-YNAB-Api-Version": _API_VERSION,
        "X-YNAB-Device-OS": "web",
        "X-Session-Token": session_token,
        "Cookie": cookie,
    }
    async with session.post(
        _SYNC_URL,
        data={
            "operation_name": "syncBudgetData",
            "request_data": json.dumps(request_data),
        },
        headers=headers,
    ) as response:
        response.raise_for_status()
        payload: dict[str, Any] = await response.json()

    if e := payload.get("error"):
        raise RuntimeError(f"YNAB rejected sync request: {e}")
    return payload


def _build_payee_tombstone(payee_id: str, payee_name: str) -> dict[str, Any]:
    return {
        "id": payee_id,
        "is_tombstone": True,
        "entities_account_id": None,
        "enabled": True,
        "auto_fill_subcategory_id": None,
        "auto_fill_user_defined_subcategory_id": None,
        "auto_fill_memo": None,
        "auto_fill_amount": 0,
        "auto_fill_subcategory_enabled": True,
        "auto_fill_memo_enabled": False,
        "auto_fill_amount_enabled": False,
        "rename_on_import_enabled": True,
        "name": payee_name,
        "internal_name": None,
    }


async def delete_payee(
    session: aiohttp.ClientSession,
    *,
    cookie: str,
    session_token: str,
    budget_version_id: str,
    payee_id: str,
    payee_name: str,
    starting_device_knowledge: int,
    ending_device_knowledge: int,
    device_knowledge_of_server: int,
) -> dict[str, Any]:
    return await _sync_budget_data(
        session,
        cookie=cookie,
        session_token=session_token,
        budget_version_id=budget_version_id,
        starting_device_knowledge=starting_device_knowledge,
        ending_device_knowledge=ending_device_knowledge,
        device_knowledge_of_server=device_knowledge_of_server,
        changed_entities={"be_payees": [_build_payee_tombstone(payee_id, payee_name)]},
    )


__all__ = ["delete_payee"]
