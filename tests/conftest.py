import os
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from manager_for_ynab._auth import _ENV_TOKEN
from manager_for_ynab.delete_payees._browser_session import _ENV_SESSION_TOKEN

if TYPE_CHECKING:
    from collections.abc import Iterator

_DEFAULT_TOKEN = "token"


@pytest.fixture(autouse=True)
def _token_env(request: pytest.FixtureRequest) -> Iterator[None]:
    marker = request.node.get_closest_marker("token_env")
    value = marker.args[0] if marker else _DEFAULT_TOKEN
    with patch.dict("os.environ", {_ENV_TOKEN: value}):
        yield


def _marked_env(
    request: pytest.FixtureRequest, marker_name: str, env_var: str
) -> Iterator[None]:
    marker = request.node.get_closest_marker(marker_name)
    if marker is None:
        yield
        return

    value = marker.args[0]
    with patch.dict("os.environ", {}, clear=False):
        if value is None:
            os.environ.pop(env_var, None)
        else:
            os.environ[env_var] = value
        yield


@pytest.fixture(autouse=True)
def _session_token_env(request: pytest.FixtureRequest) -> Iterator[None]:
    yield from _marked_env(request, "session_token_env", _ENV_SESSION_TOKEN)
