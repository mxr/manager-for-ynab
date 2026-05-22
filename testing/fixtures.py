import sqlite3
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest


_DDL_SQL = (
    files("sqlite_export_for_ynab.ddl").joinpath("create-relations.sql").read_text()
)


def apply_ddl(con: sqlite3.Connection) -> None:
    con.executescript(_DDL_SQL)


PLAN_ID_1 = str(uuid4())
_TESTING = Path(__file__).parent
_SEED_SQL = _TESTING / "seed.sql"
PLAN_ID = "a20542ae-bb3e-4282-8b3e-df3bdea4be10"
CHECKING_ACCOUNT_ID = "8fe2a49b-17b9-47a1-8aaa-c60d661e7f25"
CREDIT_CARD_ACCOUNT_ID = "ab56a1c8-439e-4eaf-931b-37f2d68d1cf5"
READY_TO_ASSIGN_CATEGORY_ID = "33333333-3333-3333-3333-333333333333"
CREDIT_CARD_CATEGORY_ID = "55555555-5555-5555-5555-555555555555"
DINING_OUT_CATEGORY_ID = "77777777-7777-7777-7777-777777777777"
DUPLICATE_CREDIT_CARD_CATEGORY_ID = "88888888-8888-8888-8888-888888888888"
EMPLOYER_PAYEE_ID = "22222222-2222-2222-2222-222222222222"
TRANSFER_PAYEE_ID = "99999999-9999-9999-9999-999999999999"
TEST_PLAN_ID_1 = "plan-1"
TEST_PLAN_ID_2 = "plan-2"
SEED_IDS: dict[str, Any] = {
    "plan_id": PLAN_ID,
    "checking_account_id": CHECKING_ACCOUNT_ID,
    "credit_card_account_id": CREDIT_CARD_ACCOUNT_ID,
    "ready_to_assign_category_id": READY_TO_ASSIGN_CATEGORY_ID,
    "credit_card_category_id": CREDIT_CARD_CATEGORY_ID,
    "dining_out_category_id": DINING_OUT_CATEGORY_ID,
    "duplicate_credit_card_category_id": DUPLICATE_CREDIT_CARD_CATEGORY_ID,
    "employer_payee_id": EMPLOYER_PAYEE_ID,
    "transfer_payee_id": TRANSFER_PAYEE_ID,
    "test_plan_id_1": TEST_PLAN_ID_1,
    "test_plan_id_2": TEST_PLAN_ID_2,
}


def seed_sql(*extra_paths: Path) -> str:
    return "\n".join(path.read_text() for path in (_SEED_SQL, *extra_paths))


def execute_seed(con: sqlite3.Connection, *extra_paths: Path) -> None:
    apply_ddl(con)
    for statement in seed_sql(*extra_paths).split(";"):
        statement = statement.strip()
        if statement:
            con.execute(statement, SEED_IDS)


@pytest.fixture()
def db(tmpdir):
    path = tmpdir / "db.sqlite"
    with sqlite3.connect(path) as con:
        execute_seed(
            con, _TESTING.parent / "tests" / "reconciler" / "seed-transactions.sql"
        )
    yield str(path)


TOKEN = f"token-{uuid4()}"
TOKEN_OVERRIDE = f"token-{uuid4()}"
