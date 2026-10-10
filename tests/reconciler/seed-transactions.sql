INSERT INTO accounts (
    id
    , plan_id
    , balance
    , cleared_balance
    , closed
    , deleted
    , name
    , type
) VALUES
(
    '1b6f0c1e-3a52-4d7e-9c41-7f2a5e8d9b10'
    , :plan_id
    , 430000
    , 430000
    , 0
    , 0
    , 'Joint'
    , 'checking'
)
, (
    '4c8e2d7a-5f13-4b9e-a6d2-0e1f3c5b7a92'
    , :plan_id
    , 430000
    , 430000
    , 0
    , 0
    , 'Savings'
    , 'savings'
)
, (
    '7d2a9f4b-8e61-4c3a-b5f7-2c9e0a1d4b63'
    , :plan_id
    , -200000
    , -200000
    , 0
    , 0
    , 'Store Card'
    , 'creditCard'
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
, (
    '5b0c1f8e-6d3a-4e2b-9f7c-2a1d8e4b6c30'
    , :plan_id
    , :checking_account_id
    , 'Checking'
    , '2025-08-01'
    , 5000
    , '-$5.00'
    , 'Payee'
    , 'uncleared'
    , 0
    , NULL
    , 0
)
, (
    '2fdaf0fc-635f-4953-b712-0854f8a0c86b'
    , :plan_id
    , '1b6f0c1e-3a52-4d7e-9c41-7f2a5e8d9b10'
    , 'Joint'
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
    '5479e2d1-edc1-4377-83a9-90468f8e46f0'
    , :plan_id
    , '1b6f0c1e-3a52-4d7e-9c41-7f2a5e8d9b10'
    , 'Joint'
    , '2025-08-01'
    , 30000
    , '-$30.00'
    , 'Payee'
    , 'uncleared'
    , 1
    , NULL
    , 0
)
, (
    '3bda5178-c78b-44b8-b39e-fd032a3d08db'
    , :plan_id
    , '1b6f0c1e-3a52-4d7e-9c41-7f2a5e8d9b10'
    , 'Joint'
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
    'e15a498a-9dbe-44fe-a79f-f2e53132de2d'
    , :plan_id
    , '1b6f0c1e-3a52-4d7e-9c41-7f2a5e8d9b10'
    , 'Joint'
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
    'db08115f-97e7-403a-a1c9-5db6d92533a5'
    , :plan_id
    , '1b6f0c1e-3a52-4d7e-9c41-7f2a5e8d9b10'
    , 'Joint'
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
    '6fea919a-446a-4cbb-9be1-45c7da71bd29'
    , :plan_id
    , '4c8e2d7a-5f13-4b9e-a6d2-0e1f3c5b7a92'
    , 'Savings'
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
    'cc39760f-6992-4bf5-b5bb-da8dc5c53685'
    , :plan_id
    , '4c8e2d7a-5f13-4b9e-a6d2-0e1f3c5b7a92'
    , 'Savings'
    , '2025-08-01'
    , 30000
    , '-$30.00'
    , 'Payee'
    , 'reconciled'
    , 1
    , NULL
    , 0
)
, (
    'c6a9c2c3-8829-4695-b452-5895d3000439'
    , :plan_id
    , '4c8e2d7a-5f13-4b9e-a6d2-0e1f3c5b7a92'
    , 'Savings'
    , '2025-08-01'
    , 60000
    , '-$60.00'
    , 'Payee'
    , 'reconciled'
    , 1
    , NULL
    , 0
)
, (
    'd86959fc-658a-4181-93d4-dd93381d2a96'
    , :plan_id
    , '4c8e2d7a-5f13-4b9e-a6d2-0e1f3c5b7a92'
    , 'Savings'
    , '2025-08-01'
    , 20000
    , '-$20.00'
    , 'Payee'
    , 'reconciled'
    , 1
    , NULL
    , 0
)
, (
    'c4384753-7361-483b-bcaa-88bf35241997'
    , :plan_id
    , '4c8e2d7a-5f13-4b9e-a6d2-0e1f3c5b7a92'
    , 'Savings'
    , '2025-08-01'
    , 10000
    , '-$10.00'
    , 'Payee'
    , 'reconciled'
    , 1
    , NULL
    , 0
)
, (
    'e95b36ff-1813-4dd9-8956-8745333820db'
    , :plan_id
    , '7d2a9f4b-8e61-4c3a-b5f7-2c9e0a1d4b63'
    , 'Store Card'
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
    'da2831a0-1da6-40a1-a7f6-6321b5f97d4a'
    , :plan_id
    , '7d2a9f4b-8e61-4c3a-b5f7-2c9e0a1d4b63'
    , 'Store Card'
    , '2025-08-01'
    , -30000
    , '$30.00'
    , 'Payee'
    , 'uncleared'
    , 1
    , NULL
    , 0
)
, (
    'f56b68e1-042d-4219-a9da-52500475aa42'
    , :plan_id
    , '7d2a9f4b-8e61-4c3a-b5f7-2c9e0a1d4b63'
    , 'Store Card'
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
    '1fb1a5bb-2f42-4040-aee2-81f7ef1131c1'
    , :plan_id
    , '7d2a9f4b-8e61-4c3a-b5f7-2c9e0a1d4b63'
    , 'Store Card'
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
    '56d2a561-98ca-4ad9-8285-2f62034a4ec8'
    , :plan_id
    , '7d2a9f4b-8e61-4c3a-b5f7-2c9e0a1d4b63'
    , 'Store Card'
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
