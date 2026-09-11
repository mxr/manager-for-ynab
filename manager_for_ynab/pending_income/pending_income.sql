SELECT
    transactions.id
    , transactions.plan_id
    , transactions.account_id
    , transactions.account_name
    , transactions.payee_id
    , transactions.payee_name
    , transactions.amount
    , transactions.amount_formatted
    , transactions.category_id
    , transactions.memo
    , transactions.cleared
    , transactions.approved
    , transactions.flag_color
    , transactions."date"
    , subtransactions.id AS subtransaction_id
    , subtransactions.amount AS subtransaction_amount
    , subtransactions.payee_id AS subtransaction_payee_id
    , subtransactions.payee_name AS subtransaction_payee_name
    , subtransactions.category_id AS subtransaction_category_id
    , subtransactions.memo AS subtransaction_memo
FROM transactions
LEFT JOIN subtransactions
    ON
        transactions.id = subtransactions.transaction_id
        AND NOT subtransactions.deleted
WHERE
    TRUE
    AND transactions.cleared = 'uncleared'
    AND transactions."date" < DATE('now', 'localtime')
    AND transactions.amount > 0
    AND NOT transactions.deleted
    AND transactions.id NOT IN (
        SELECT transfer_legs.transfer_transaction_id
        FROM subtransactions AS transfer_legs
        WHERE
            transfer_legs.transfer_transaction_id IS NOT NULL
            AND NOT transfer_legs.deleted
    )
    AND SUBSTR(transactions."date", 1, 7)
    = SUBSTR(DATE('now', 'localtime'), 1, 7)
    AND (:skip_matched = 0 OR transactions.matched_transaction_id IS NULL)
ORDER BY
    transactions."date" ASC
    , transactions.account_name ASC
    , transactions.payee_name ASC
    , transactions.amount DESC
    , subtransactions.id ASC
;
