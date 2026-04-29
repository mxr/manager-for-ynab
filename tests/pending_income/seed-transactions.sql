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
    , DATE('now', 'localtime', '-1 day')
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
    , DATE('now', 'localtime', '-1 day')
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
    , DATE('now', 'localtime', '-1 day')
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
    , DATE('now', 'localtime', '-1 day')
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
    'transfer'
    , :test_plan_id_1
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
, (
    'matched'
    , :test_plan_id_1
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
