import pytest

from manager_for_ynab._main import build_parser
from manager_for_ynab._main import main


def test_main_requires_subcommand():
    with pytest.raises(SystemExit) as excinfo:
        main(())

    assert excinfo.value.code == 2


def test_main_dispatches_reconciler(monkeypatch):
    called: dict[str, object] = {}

    def fake_main(argv, *, prog):
        called["argv"] = argv
        called["prog"] = prog
        return 0

    monkeypatch.setattr("manager_for_ynab._main.reconciler_main.main", fake_main)

    ret = main(("reconciler", "--for-real", "--target", "500"))

    assert ret == 0
    assert called == {
        "argv": ["--for-real", "--target", "500"],
        "prog": "manager-for-ynab reconciler",
    }


def test_main_dispatches_pending_income(monkeypatch):
    called: dict[str, object] = {}

    def fake_main(argv, *, prog):
        called["argv"] = argv
        called["prog"] = prog
        return 0

    monkeypatch.setattr("manager_for_ynab._main.pending_income.main", fake_main)

    ret = main(("pending-income", "--for-real"))

    assert ret == 0
    assert called == {
        "argv": ["--for-real"],
        "prog": "manager-for-ynab pending-income",
    }


def test_build_parser_registers_expected_subcommands():
    parser = build_parser()
    actions = [action for action in parser._actions if action.dest == "command"]
    assert len(actions) == 1
    assert actions[0].choices is not None
    assert set(actions[0].choices) == {"pending-income", "reconciler"}
