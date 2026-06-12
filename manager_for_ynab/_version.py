import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version
from pathlib import Path


def get_version(distribution: str = "manager_for_ynab") -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        with open(Path(__file__).resolve().parent.parent / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
