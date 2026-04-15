import pytest

from manager_for_ynab._main import build_parser
from manager_for_ynab._main import main


def test_main_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("--version",))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert out == "manager-for-ynab 1.0.0\n"


def test_main_requires_subcommand():
    with pytest.raises(SystemExit) as excinfo:
        main(())

    assert excinfo.value.code == 2


def test_main_reconciler_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("reconciler", "--help"))

    assert excinfo.value.code == 0
    out, _ = capsys.readouterr()
    assert "manager-for-ynab reconciler" in out
    assert "Find and automatically reconciles unreconciled transactions." in out
    assert "--for-real" in out


def test_build_parser_registers_expected_subcommands():
    parser = build_parser()
    actions = [action for action in parser._actions if action.dest == "command"]
    assert len(actions) == 1
    assert actions[0].choices is not None
    assert set(actions[0].choices) == {"reconciler"}
