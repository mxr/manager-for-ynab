import os


_ENV_TOKEN = "YNAB_PERSONAL_ACCESS_TOKEN"


def resolve_token(token_override: str | None = None) -> str:
    token = token_override or os.environ.get(_ENV_TOKEN)
    if token:
        return token

    raise ValueError(
        f"Must set YNAB access token as {_ENV_TOKEN!r} environment variable or pass token_override directly. See https://api.ynab.com/#personal-access-tokens"
    )


__all__ = [resolve_token.__name__, _ENV_TOKEN]
