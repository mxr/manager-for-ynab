SELECT
    transactions.id
    , transactions.matched_transaction_id
    , transactions.plan_id
    , transactions.account_name
    , transactions.payee_name
    , transactions.amount_formatted
    , transactions."date"
FROM transactions
WHERE
    transactions.deleted = 0
    AND transactions.approved = 0
    AND transactions.matched_transaction_id IS NOT NULL
    AND transactions.id < transactions.matched_transaction_id
ORDER BY
    transactions."date"
    , transactions.account_name
    , transactions.payee_name
    , transactions.id
;
