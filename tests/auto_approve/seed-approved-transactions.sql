INSERT INTO transactions (
    id
    , plan_id
    , account_id
    , account_name
    , "date"
    , amount
    , amount_formatted
    , payee_name
    , import_payee_name
    , cleared
    , approved
    , matched_transaction_id
    , deleted
) VALUES
(
    'approved-1'
    , :test_plan_id_1
    , NULL
    , 'Checking'
    , '2026-04-21'
    , -3000
    , '-$3.00'
    , 'Done'
    , NULL
    , 'uncleared'
    , 1
    , 'approved-2'
    , 0
)
, (
    'approved-2'
    , :test_plan_id_1
    , NULL
    , 'Checking'
    , '2026-04-21'
    , -3000
    , '-$3.00'
    , 'Done'
    , '{"payee_name": "Done"}'
    , 'uncleared'
    , 1
    , 'approved-1'
    , 0
)
, (
    'unmatched'
    , :test_plan_id_1
    , NULL
    , 'Checking'
    , '2026-04-21'
    , -7000
    , '-$7.00'
    , 'Solo'
    , NULL
    , 'cleared'
    , 1
    , NULL
    , 0
)
;
