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
    AND (
        (
            transactions.matched_transaction_id IS NOT NULL
            -- matched pairs reference each other
            -- so keep one stable row per pair
            AND transactions.id < transactions.matched_transaction_id
        )
        OR EXISTS (
            SELECT 1
            FROM scheduled_transactions
            WHERE
                scheduled_transactions.plan_id = transactions.plan_id
                AND scheduled_transactions.deleted = 0
                AND scheduled_transactions.account_name
                = transactions.account_name
                AND scheduled_transactions.payee_name = transactions.payee_name
                AND scheduled_transactions.amount = transactions.amount
                AND DATE(scheduled_transactions.date_next)
                = DATE(transactions."date", '+1 month')
        )
    )
ORDER BY
    transactions."date" ASC
    , transactions.account_name ASC
    , transactions.payee_name ASC
    , transactions.amount DESC
;
