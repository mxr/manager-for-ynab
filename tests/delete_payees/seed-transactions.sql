INSERT INTO transactions (
    id
    , plan_id
    , payee_id
    , deleted
) VALUES (
    'delete-payees-txn-live'
    , :plan_id
    , :employer_payee_id
    , 0
)
;

INSERT INTO subtransactions (
    id
    , plan_id
    , payee_id
    , deleted
) VALUES (
    'delete-payees-subtxn-live'
    , :plan_id
    , :employer_payee_id
    , 0
)
;

INSERT INTO scheduled_transactions (
    id
    , plan_id
    , payee_id
    , deleted
) VALUES (
    'delete-payees-sched-txn-live'
    , :plan_id
    , :employer_payee_id
    , 0
)
;

INSERT INTO scheduled_subtransactions (
    id
    , plan_id
    , payee_id
    , deleted
) VALUES (
    'delete-payees-sched-subtxn-live'
    , :plan_id
    , :employer_payee_id
    , 0
)
;

INSERT INTO transactions (
    id
    , plan_id
    , payee_id
    , deleted
) VALUES (
    'delete-payees-txn-deleted'
    , :plan_id
    , :transfer_payee_id
    , 1
)
;
