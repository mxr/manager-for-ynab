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
) VALUES
(
    'sched-solo'
    , :test_plan_id_1
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
) VALUES
(
    'pair-a-1'
    , :test_plan_id_1
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
, (
    'pair-a-2'
    , :test_plan_id_1
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
, (
    'pair-b-1'
    , :test_plan_id_2
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
, (
    'pair-b-2'
    , :test_plan_id_2
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
, (
    'approved-1'
    , :test_plan_id_1
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
, (
    'approved-2'
    , :test_plan_id_1
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
, (
    'unmatched'
    , :test_plan_id_1
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
, (
    'deleted-1'
    , :test_plan_id_1
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
, (
    'deleted-2'
    , :test_plan_id_1
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
