CREATE TABLE plans (
    id TEXT PRIMARY KEY
    , name TEXT
    , currency_format_currency_symbol TEXT
    , currency_format_iso_code TEXT
)
;

INSERT INTO plans VALUES (
    'a20542ae-bb3e-4282-8b3e-df3bdea4be10'
    , 'My Plan'
    , '$'
    , 'USD'
)
;

CREATE TABLE accounts (
    id TEXT PRIMARY KEY
    , plan_id TEXT
    , cleared_balance INT
    , closed BOOLEAN
    , deleted BOOLEAN
    , name TEXT
    , type TEXT
)
;

INSERT INTO accounts VALUES (
    '8fe2a49b-17b9-47a1-8aaa-c60d661e7f25'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , 430000
    , 0
    , 0
    , 'Checking'
    , 'checking'
)
;

INSERT INTO accounts VALUES (
    'ab56a1c8-439e-4eaf-931b-37f2d68d1cf5'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , -200000
    , 0
    , 0
    , 'Credit Card'
    , 'creditCard'
)
;

CREATE TABLE categories (
    id TEXT PRIMARY KEY
    , plan_id TEXT
    , deleted BOOLEAN
    , category_group_name TEXT
    , name TEXT
)
;

INSERT INTO categories VALUES (
    '33333333-3333-3333-3333-333333333333'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , 0
    , 'Inflow'
    , 'Inflow: Ready to Assign'
)
;

INSERT INTO categories VALUES (
    '55555555-5555-5555-5555-555555555555'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , 0
    , 'Credit Card Payments'
    , 'Credit Card'
)
;

CREATE TABLE payees (
    id TEXT PRIMARY KEY
    , plan_id TEXT
    , deleted BOOLEAN
    , name TEXT
    , transfer_account_id TEXT
)
;

INSERT INTO payees VALUES (
    '22222222-2222-2222-2222-222222222222'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , 0
    , 'Employer'
    , NULL
)
;

CREATE TABLE transactions (
    id TEXT PRIMARY KEY
    , plan_id TEXT
    , account_id TEXT
    , account_name TEXT
    , "date" TEXT
    , amount INT
    , amount_formatted TEXT
    , payee_name TEXT
    , cleared TEXT
    , approved BOOLEAN
    , matched_transaction_id TEXT
    , deleted BOOLEAN
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'ae3d9f6b-07f1-4c49-9137-5133c8bf0500'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , (
        SELECT id
        FROM accounts
        WHERE name = 'Checking'
        ORDER BY id LIMIT 1
    )
    , 'Checking'
    , '2025-08-01'
    , 400000
    , '-$400.00'
    , 'Payee'
    , 'reconciled'
    , 1
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    '9a97f337-28db-4c2d-990f-d9ec0e9bc765'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , (
        SELECT id
        FROM accounts
        WHERE name = 'Checking'
        ORDER BY id LIMIT 1
    )
    , 'Checking'
    , '2025-08-01'
    , 30000
    , '-$30.00'
    , 'Payee'
    , 'cleared'
    , 1
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'c479c335-b54f-48b9-8b74-49a907f1b3f2'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , (
        SELECT id
        FROM accounts
        WHERE name = 'Checking'
        ORDER BY id LIMIT 1
    )
    , 'Checking'
    , '2025-08-01'
    , 60000
    , '-$60.00'
    , 'Payee'
    , 'uncleared'
    , 1
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    '96817e5f-d272-4012-9790-38f8a8e2be90'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , (
        SELECT id
        FROM accounts
        WHERE name = 'Checking'
        ORDER BY id LIMIT 1
    )
    , 'Checking'
    , '2025-08-01'
    , 20000
    , '-$20.00'
    , 'Payee'
    , 'uncleared'
    , 1
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'eeef0922-b226-4f8a-bf00-66d4d98e348c'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , (
        SELECT id
        FROM accounts
        WHERE name = 'Checking'
        ORDER BY id LIMIT 1
    )
    , 'Checking'
    , '2025-08-01'
    , 10000
    , '-$10.00'
    , 'Payee'
    , 'uncleared'
    , 1
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    '21c45599-4113-4888-9969-66d42553d870'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , (
        SELECT id
        FROM accounts
        WHERE name = 'Credit Card'
        ORDER BY id LIMIT 1
    )
    , 'Credit Card'
    , '2025-08-01'
    , -400000
    , '$400.00'
    , 'Payee'
    , 'reconciled'
    , 1
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    '956ff61f-b0e4-4f36-bf7d-f31d008ff7e4'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , (
        SELECT id
        FROM accounts
        WHERE name = 'Credit Card'
        ORDER BY id LIMIT 1
    )
    , 'Credit Card'
    , '2025-08-01'
    , -30000
    , '$30.00'
    , 'Payee'
    , 'cleared'
    , 1
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'c9ca467d-e89d-4d0d-8356-f37d4f798c5f'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , (
        SELECT id
        FROM accounts
        WHERE name = 'Credit Card'
        ORDER BY id LIMIT 1
    )
    , 'Credit Card'
    , '2025-08-01'
    , -60000
    , '$60.00'
    , 'Payee'
    , 'uncleared'
    , 1
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    '258b33fb-a2b2-4833-9274-05697c68ff1d'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , (
        SELECT id
        FROM accounts
        WHERE name = 'Credit Card'
        ORDER BY id LIMIT 1
    )
    , 'Credit Card'
    , '2025-08-01'
    , -20000
    , '$20.00'
    , 'Payee'
    , 'uncleared'
    , 1
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'd9faa297-f59e-4516-bcbf-664b298ff09e'
    , (
        SELECT id
        FROM plans
        ORDER BY id LIMIT 1
    )
    , (
        SELECT id
        FROM accounts
        WHERE name = 'Credit Card'
        ORDER BY id LIMIT 1
    )
    , 'Credit Card'
    , '2025-08-01'
    , -10000
    , '$10.00'
    , 'Payee'
    , 'uncleared'
    , 1
    , NULL
    , 0
)
;

CREATE TABLE subtransactions (
    transfer_transaction_id TEXT
    , deleted BOOLEAN
)
;

CREATE TABLE scheduled_transactions (
    id TEXT PRIMARY KEY
    , plan_id TEXT
    , account_id TEXT
    , account_name TEXT
    , amount INT
    , amount_formatted TEXT
    , amount_currency REAL
    , category_id TEXT
    , category_name TEXT
    , date_first TEXT
    , date_next TEXT
    , deleted BOOLEAN
    , flag_color TEXT
    , flag_name TEXT
    , frequency TEXT
    , memo TEXT
    , payee_id TEXT
    , payee_name TEXT
    , transfer_account_id TEXT
)
;

INSERT INTO scheduled_transactions (
    id
    , plan_id
    , account_id
    , account_name
    , amount
    , amount_formatted
    , amount_currency
    , category_id
    , category_name
    , date_first
    , date_next
    , deleted
    , flag_color
    , flag_name
    , frequency
    , memo
    , payee_id
    , payee_name
    , transfer_account_id
) VALUES (
    'sched-solo'
    , 'plan-1'
    , NULL
    , 'Checking'
    , -7000
    , '-$7.00'
    , -7.0
    , NULL
    , NULL
    , '2026-04-21'
    , '2026-05-21'
    , 0
    , NULL
    , NULL
    , 'monthly'
    , NULL
    , NULL
    , 'Solo'
    , NULL
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'keep-1'
    , 'plan-1'
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', '-1 day')
    , 100000
    , '$100.00'
    , 'Employer'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'keep-2'
    , 'plan-2'
    , NULL
    , 'Savings'
    , DATE('now', 'localtime', '-1 day')
    , 55000
    , '$55.00'
    , 'Employer'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'future'
    , 'plan-1'
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', '+1 day')
    , 50000
    , '$50.00'
    , 'Future'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'negative'
    , 'plan-1'
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', '-1 day')
    , -20000
    , '-$20.00'
    , 'Refund'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'cleared'
    , 'plan-1'
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', '-1 day')
    , 10000
    , '$10.00'
    , 'Cleared'
    , 'cleared'
    , 0
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'prior-month'
    , 'plan-1'
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', 'start of month', '-1 month')
    , 30000
    , '$30.00'
    , 'Old'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'transfer'
    , 'plan-1'
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', '-1 day')
    , 40000
    , '$40.00'
    , 'Transfer'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'matched'
    , 'plan-1'
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', '-1 day')
    , 65000
    , '$65.00'
    , 'Employer'
    , 'uncleared'
    , 1
    , 'matched-peer'
    , 0
)
;

INSERT INTO subtransactions VALUES ('transfer', 0);

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'pair-a-1'
    , 'plan-1'
    , NULL
    , 'Checking'
    , '2026-04-20'
    , -4500
    , '-$4.50'
    , 'Coffee'
    , 'uncleared'
    , 0
    , 'pair-a-2'
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'pair-a-2'
    , 'plan-1'
    , NULL
    , 'Checking'
    , '2026-04-20'
    , -4500
    , '-$4.50'
    , 'Coffee'
    , 'uncleared'
    , 0
    , 'pair-a-1'
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'pair-b-1'
    , 'plan-2'
    , NULL
    , 'Card'
    , '2026-04-21'
    , -12000
    , '-$12.00'
    , 'Lunch'
    , 'uncleared'
    , 0
    , 'pair-b-2'
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'pair-b-2'
    , 'plan-2'
    , NULL
    , 'Card'
    , '2026-04-21'
    , -12000
    , '-$12.00'
    , 'Lunch'
    , 'uncleared'
    , 0
    , 'pair-b-1'
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'approved-1'
    , 'plan-1'
    , NULL
    , 'Checking'
    , '2026-04-21'
    , -3000
    , '-$3.00'
    , 'Done'
    , 'uncleared'
    , 1
    , 'approved-2'
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'approved-2'
    , 'plan-1'
    , NULL
    , 'Checking'
    , '2026-04-21'
    , -3000
    , '-$3.00'
    , 'Done'
    , 'uncleared'
    , 0
    , 'approved-1'
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'unmatched'
    , 'plan-1'
    , NULL
    , 'Checking'
    , '2026-04-21'
    , -7000
    , '-$7.00'
    , 'Solo'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'deleted-1'
    , 'plan-1'
    , NULL
    , 'Checking'
    , '2026-04-21'
    , -5000
    , '-$5.00'
    , 'Gone'
    , 'uncleared'
    , 0
    , 'deleted-2'
    , 1
)
;

INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES (
    'deleted-2'
    , 'plan-1'
    , NULL
    , 'Checking'
    , '2026-04-21'
    , -5000
    , '-$5.00'
    , 'Gone'
    , 'uncleared'
    , 0
    , 'deleted-1'
    , 0
)
;
