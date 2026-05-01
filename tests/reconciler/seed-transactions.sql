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
    'ae3d9f6b-07f1-4c49-9137-5133c8bf0500'
    , :plan_id
    , :checking_account_id
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
, (
    '9a97f337-28db-4c2d-990f-d9ec0e9bc765'
    , :plan_id
    , :checking_account_id
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
, (
    'c479c335-b54f-48b9-8b74-49a907f1b3f2'
    , :plan_id
    , :checking_account_id
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
, (
    '96817e5f-d272-4012-9790-38f8a8e2be90'
    , :plan_id
    , :checking_account_id
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
, (
    'eeef0922-b226-4f8a-bf00-66d4d98e348c'
    , :plan_id
    , :checking_account_id
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
, (
    '21c45599-4113-4888-9969-66d42553d870'
    , :plan_id
    , :credit_card_account_id
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
, (
    '956ff61f-b0e4-4f36-bf7d-f31d008ff7e4'
    , :plan_id
    , :credit_card_account_id
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
, (
    'c9ca467d-e89d-4d0d-8356-f37d4f798c5f'
    , :plan_id
    , :credit_card_account_id
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
, (
    '258b33fb-a2b2-4833-9274-05697c68ff1d'
    , :plan_id
    , :credit_card_account_id
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
, (
    'd9faa297-f59e-4516-bcbf-664b298ff09e'
    , :plan_id
    , :credit_card_account_id
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
