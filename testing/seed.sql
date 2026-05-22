INSERT INTO plans (
    id
    , name
    , currency_format_currency_symbol
    , currency_format_iso_code
) VALUES (
    :plan_id
    , 'My Plan'
    , '$'
    , 'USD'
)
;

INSERT INTO accounts (
    id
    , plan_id
    , cleared_balance
    , closed
    , deleted
    , name
    , type
) VALUES (
    :checking_account_id
    , :plan_id
    , 430000
    , 0
    , 0
    , 'Checking'
    , 'checking'
)
;

INSERT INTO accounts (
    id
    , plan_id
    , cleared_balance
    , closed
    , deleted
    , name
    , type
) VALUES (
    :credit_card_account_id
    , :plan_id
    , -200000
    , 0
    , 0
    , 'Credit Card'
    , 'creditCard'
)
;

INSERT INTO categories (
    id
    , plan_id
    , deleted
    , category_group_name
    , name
) VALUES (
    :ready_to_assign_category_id
    , :plan_id
    , 0
    , 'Inflow'
    , 'Inflow: Ready to Assign'
)
;

INSERT INTO categories (
    id
    , plan_id
    , deleted
    , category_group_name
    , name
) VALUES (
    :credit_card_category_id
    , :plan_id
    , 0
    , 'Credit Card Payments'
    , 'Credit Card'
)
;

INSERT INTO categories (
    id
    , plan_id
    , deleted
    , category_group_name
    , name
) VALUES (
    :dining_out_category_id
    , :plan_id
    , 0
    , 'Dining'
    , 'Dining Out'
)
;

INSERT INTO categories (
    id
    , plan_id
    , deleted
    , category_group_name
    , name
) VALUES (
    :duplicate_credit_card_category_id
    , :plan_id
    , 1
    , 'Credit Card Payments'
    , 'Credit Card'
)
;

INSERT INTO payees (
    id
    , plan_id
    , deleted
    , name
    , transfer_account_id
) VALUES (
    :employer_payee_id
    , :plan_id
    , 0
    , 'Employer'
    , NULL
)
;

INSERT INTO payees (
    id
    , plan_id
    , deleted
    , name
    , transfer_account_id
) VALUES (
    :transfer_payee_id
    , :plan_id
    , 0
    , 'Transfer'
    , :checking_account_id
)
;
