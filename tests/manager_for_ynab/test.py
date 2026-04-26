import sys
from configparser import ConfigParser
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch

import pytest

from manager_for_ynab import _version
from manager_for_ynab._main import build_parser
from manager_for_ynab._main import main


def raising_version(distribution: str) -> str:
    raise PackageNotFoundError(distribution)


def test_main_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("--version",))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert out == f"manager-for-ynab {_version.get_version()}\n"


@patch.object(sys, "argv", ["manager-for-ynab"])
def test_main_without_args_prints_help(capsys):
    assert main() == 0

    out, _ = capsys.readouterr()
    assert "usage: manager-for-ynab" in out
    assert "auto-approve" in out
    assert "reconciler" in out
    assert "pending-income" in out
    assert "zero-out" in out


@patch.object(sys, "argv", ["manager-for-ynab", "--version"])
def test_main_defaults_to_sys_argv():
    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 0


def test_main_reconciler_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("reconciler", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab reconciler" in out
    assert "Find and automatically reconciles unreconciled transactions." in out
    assert "--for-real" in out


def test_main_pending_income_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("pending-income", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab pending-income" in out
    assert "--for-real" in out


def test_main_auto_approve_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("auto-approve", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab auto-approve" in out
    assert "--for-real" in out


def test_main_zero_out_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("zero-out", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab zero-out" in out
    assert "--for-real" in out


def test_build_parser_registers_expected_subcommands():
    parser = build_parser()
    actions = [action for action in parser._actions if action.dest == "command"]
    assert len(actions) == 1
    assert actions[0].choices is not None
    assert set(actions[0].choices) == {
        "auto-approve",
        "pending-income",
        "reconciler",
        "zero-out",
    }


@patch.object(_version, "version", lambda distribution: f"{distribution}-version")
def test_get_version_from_installed_metadata():
    assert _version.get_version("custom-dist") == "custom-dist-version"


@patch.object(_version, "version", raising_version)
def test_get_version_falls_back_to_setup_cfg():
    config = ConfigParser()
    config.read(Path(__file__).parents[2] / "setup.cfg")

    assert _version.get_version() == config["metadata"]["version"]
