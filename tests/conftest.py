from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from manager_for_ynab._auth import _ENV_TOKEN

if TYPE_CHECKING:
    from collections.abc import Iterator

_DEFAULT_TOKEN = "token"


@pytest.fixture(autouse=True)
def _token_env(request: pytest.FixtureRequest) -> Iterator[None]:
    marker = request.node.get_closest_marker("token_env")
    value = marker.args[0] if marker else _DEFAULT_TOKEN
    with patch.dict("os.environ", {_ENV_TOKEN: value}):
        yield
