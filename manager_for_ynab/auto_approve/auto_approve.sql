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
    -- matched pairs reference each other
    -- so keep one stable row per pair
    AND transactions.id < transactions.matched_transaction_id
ORDER BY
    transactions."date" ASC
    , transactions.account_name ASC
    , transactions.payee_name ASC
    , transactions.amount DESC
;
