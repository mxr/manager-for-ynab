INSERT INTO plans (
    id
    , name
) VALUES (
    'other-plan'
    , 'Other Plan'
)
;

INSERT INTO payees (
    id
    , plan_id
    , deleted
    , name
    , transfer_account_id
) VALUES (
    'other-plan-payee'
    , 'other-plan'
    , 0
    , 'Other Payee'
    , NULL
)
;

INSERT INTO transactions (
    id
    , plan_id
    , payee_id
    , deleted
) VALUES (
    'other-plan-txn'
    , 'other-plan'
    , 'other-plan-payee'
    , 0
)
;
