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
    , 'cleared'
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
    , 'cleared'
    , 0
    , NULL
    , 0
)
;
