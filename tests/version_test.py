from configparser import ConfigParser
from importlib.metadata import PackageNotFoundError
from pathlib import Path

from manager_for_ynab import _version


def test_get_version_from_installed_metadata(monkeypatch):
    monkeypatch.setattr(
        _version, "version", lambda distribution: f"{distribution}-version"
    )

    assert _version.get_version("custom-dist") == "custom-dist-version"


def test_get_version_falls_back_to_setup_cfg(monkeypatch):
    def raising_version(distribution):
        raise PackageNotFoundError(distribution)

    monkeypatch.setattr(_version, "version", raising_version)

    config = ConfigParser()
    config.read(Path(__file__).parent.parent / "setup.cfg")

    assert _version.get_version() == config["metadata"]["version"]
