from configparser import ConfigParser
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version
from pathlib import Path


def get_version(distribution: str = "manager_for_ynab") -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        config = ConfigParser()
        config.read(Path(__file__).resolve().parent.parent / "setup.cfg")
        return config["metadata"]["version"]
