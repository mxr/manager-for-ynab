CREATE TABLE plans (
    id TEXT PRIMARY KEY
    , name TEXT
    , currency_format_currency_symbol TEXT
    , currency_format_iso_code TEXT
)
;

INSERT INTO plans VALUES (
    :plan_id
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
    :checking_account_id
    , :plan_id
    , 430000
    , 0
    , 0
    , 'Checking'
    , 'checking'
)
;

INSERT INTO accounts VALUES (
    :credit_card_account_id
    , :plan_id
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
    :ready_to_assign_category_id
    , :plan_id
    , 0
    , 'Inflow'
    , 'Inflow: Ready to Assign'
)
;

INSERT INTO categories VALUES (
    :credit_card_category_id
    , :plan_id
    , 0
    , 'Credit Card Payments'
    , 'Credit Card'
)
;

INSERT INTO categories VALUES (
    :dining_out_category_id
    , :plan_id
    , 0
    , 'Dining'
    , 'Dining Out'
)
;

INSERT INTO categories VALUES (
    :duplicate_credit_card_category_id
    , :plan_id
    , 1
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
    :employer_payee_id
    , :plan_id
    , 0
    , 'Employer'
    , NULL
)
;

INSERT INTO payees VALUES (
    :transfer_payee_id
    , :plan_id
    , 0
    , 'Transfer'
    , :checking_account_id
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
    , import_payee_name TEXT
    , cleared TEXT
    , approved BOOLEAN
    , matched_transaction_id TEXT
    , deleted BOOLEAN
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
