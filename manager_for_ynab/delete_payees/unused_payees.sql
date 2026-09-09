WITH used_payee_ids AS (
    SELECT payee_id
    FROM transactions
    WHERE plan_id = :plan_id AND payee_id IS NOT NULL AND NOT deleted
    UNION
    SELECT payee_id
    FROM subtransactions
    WHERE plan_id = :plan_id AND payee_id IS NOT NULL AND NOT deleted
    UNION
    SELECT payee_id
    FROM scheduled_transactions
    WHERE plan_id = :plan_id AND payee_id IS NOT NULL AND NOT deleted
    UNION
    SELECT payee_id
    FROM scheduled_subtransactions
    WHERE plan_id = :plan_id AND payee_id IS NOT NULL AND NOT deleted
)

SELECT
    p.id AS payee_id
    , p.name AS payee_name
FROM payees AS p
LEFT JOIN used_payee_ids AS u ON p.id = u.payee_id
WHERE
    TRUE
    AND p.plan_id = :plan_id
    AND NOT p.deleted
    AND u.payee_id IS NULL
    AND p.transfer_account_id IS NULL
    AND p.name NOT IN (
        'Reconciliation Balance Adjustment', 'Manual Balance Adjustment'
    )
ORDER BY p.name, p.id
;
