from __future__ import annotations

import sys
import tomllib
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
    assert "pending-transaction" in out
    assert "sankey" in out
    assert "zero-out" in out
    assert "delete-payees" in out


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


def test_main_pending_transaction_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("pending-transaction", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab pending-transaction" in out
    assert "--for-real" in out


def test_main_auto_approve_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("auto-approve", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab auto-approve" in out
    assert "--for-real" in out


def test_main_add_transaction_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("add-transaction", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab add-transaction" in out
    assert "--for-real" in out


def test_main_zero_out_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("zero-out", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab zero-out" in out
    assert "--for-real" in out


def test_main_delete_payees_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("delete-payees", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab delete-payees" in out
    assert "--for-real" in out
    assert "--payee-ids" in out


def test_main_sankey_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("sankey", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab sankey" in out
    assert "--start" in out
    assert "--end" in out
    assert "--out" in out
    assert "--sort-by" in out


@pytest.mark.parametrize(
    ("command", "flag"),
    [
        pytest.param("add-transaction", "--plan-name", id="add-transaction-plan-name"),
        pytest.param(
            "add-transaction", "--account-name", id="add-transaction-account-name"
        ),
        pytest.param(
            "add-transaction", "--payee-name", id="add-transaction-payee-name"
        ),
        pytest.param(
            "add-transaction", "--category-group", id="add-transaction-category-group"
        ),
        pytest.param(
            "add-transaction", "--category-name", id="add-transaction-category-name"
        ),
        pytest.param("zero-out", "--plan-id", id="zero-out-plan-id"),
        pytest.param("zero-out", "--category-group", id="zero-out-category-group"),
        pytest.param("zero-out", "--category-name", id="zero-out-category-name"),
        pytest.param("delete-payees", "--plan-id", id="delete-payees-plan-id"),
        pytest.param("delete-payees", "--payee-ids", id="delete-payees-payee-ids"),
    ],
)
@pytest.mark.parametrize(
    "value", [pytest.param("", id="empty"), pytest.param("  ", id="whitespace")]
)
def test_main_rejects_empty_string_args(capsys, command, flag, value):
    with pytest.raises(SystemExit) as excinfo:
        main((command, flag, value))

    assert excinfo.value.code == 2
    _, err = capsys.readouterr()
    assert f"argument {flag}: must not be empty" in err


def test_build_parser_registers_expected_subcommands():
    parser = build_parser()
    actions = [action for action in parser._actions if action.dest == "command"]
    assert len(actions) == 1
    assert actions[0].choices is not None
    assert set(actions[0].choices) == {
        "auto-approve",
        "add-transaction",
        "pending-transaction",
        "reconciler",
        "sankey",
        "zero-out",
        "delete-payees",
    }


@patch.object(_version, "version", lambda distribution: f"{distribution}-version")
def test_get_version_from_installed_metadata():
    assert _version.get_version("custom-dist") == "custom-dist-version"


@patch.object(_version, "version", raising_version)
def test_get_version_falls_back_to_pyproject_toml():
    with open(Path(__file__).parents[2] / "pyproject.toml", "rb") as f:
        expected = tomllib.load(f)["project"]["version"]

    assert _version.get_version() == expected
