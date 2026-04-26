SELECT
    transactions.id
    , transactions.plan_id
    , transactions.account_name
    , transactions.payee_name
    , transactions.amount_formatted
    , transactions."date"
FROM transactions
WHERE
    TRUE
    AND transactions.cleared = 'uncleared'
    AND transactions."date" < DATE('now', 'localtime')
    AND transactions.amount > 0
    AND NOT transactions.deleted
    AND SUBSTR(transactions."date", 6, 2) = SUBSTR(DATE(), 6, 2)
    AND (:skip_matched = 0 OR transactions.matched_transaction_id IS NULL)
    AND transactions.id NOT IN (
        SELECT subtransactions.transfer_transaction_id
        FROM subtransactions
        WHERE
            subtransactions.transfer_transaction_id IS NOT NULL
            AND NOT subtransactions.deleted
    )
ORDER BY
    transactions."date" ASC
    , transactions.account_name ASC
    , transactions.payee_name ASC
    , transactions.amount DESC
;
