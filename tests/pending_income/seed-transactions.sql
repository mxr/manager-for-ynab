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
) VALUES
(
    'keep-1'
    , :test_plan_id_1
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', 'start of month')
    , 100000
    , '$100.00'
    , 'Employer'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
, (
    'keep-2'
    , :test_plan_id_2
    , NULL
    , 'Savings'
    , DATE('now', 'localtime', 'start of month')
    , 55000
    , '$55.00'
    , 'Employer'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
, (
    'future'
    , :test_plan_id_1
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
, (
    'negative'
    , :test_plan_id_1
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', 'start of month')
    , -20000
    , '-$20.00'
    , 'Refund'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
, (
    'cleared'
    , :test_plan_id_1
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', 'start of month')
    , 10000
    , '$10.00'
    , 'Cleared'
    , 'cleared'
    , 0
    , NULL
    , 0
)
, (
    'prior-month'
    , :test_plan_id_1
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
, (
    'split'
    , :test_plan_id_1
    , :checking_account_id
    , 'Checking'
    , DATE('now', 'localtime', 'start of month')
    , 40000
    , '$40.00'
    , 'Split'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
, (
    'matched'
    , :test_plan_id_1
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', 'start of month')
    , 65000
    , '$65.00'
    , 'Employer'
    , 'uncleared'
    , 1
    , 'matched-peer'
    , 0
)
, (
    'transfer-mirror-of-split'
    , :test_plan_id_1
    , NULL
    , 'Checking'
    , DATE('now', 'localtime', 'start of month')
    , 116280
    , '$116.28'
    , 'Transfer : Savings'
    , 'uncleared'
    , 1
    , NULL
    , 0
)
;

INSERT INTO subtransactions (
    id
    , transaction_id
    , amount
    , amount_formatted
    , category_id
    , payee_id
    , payee_name
    , memo
    , deleted
) VALUES
(
    'subtxn-split-1'
    , 'split'
    , 25000
    , '$25.00'
    , :dining_out_category_id
    , :employer_payee_id
    , 'Employer'
    , 'half'
    , 0
)
, (
    'subtxn-split-2'
    , 'split'
    , 15000
    , '$15.00'
    , NULL
    , NULL
    , NULL
    , 'other half'
    , 0
)
;

INSERT INTO subtransactions (
    id
    , transaction_id
    , transfer_transaction_id
    , deleted
) VALUES (
    'subtxn-split-transfer'
    , 'split-parent'
    , 'transfer-mirror-of-split'
    , 0
)
;
