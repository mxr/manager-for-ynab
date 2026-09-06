WITH used_payees AS (
    SELECT
        plan_id
        , payee_id
    FROM transactions
    WHERE
        TRUE
        AND approved
        AND payee_id IS NOT NULL
        AND NOT deleted
    UNION
    SELECT
        plan_id
        , payee_id
    FROM subtransactions
    WHERE
        TRUE
        AND payee_id IS NOT NULL
        AND NOT deleted
    UNION
    SELECT
        plan_id
        , payee_id
    FROM scheduled_transactions
    WHERE
        TRUE
        AND payee_id IS NOT NULL
        AND NOT deleted
    UNION
    SELECT
        plan_id
        , payee_id
    FROM scheduled_subtransactions
    WHERE
        TRUE
        AND payee_id IS NOT NULL
        AND NOT deleted
)

, candidates AS (
    SELECT
        p.plan_id
        , p.name
    FROM payees AS p
    LEFT JOIN used_payees AS up ON p.plan_id = up.plan_id AND p.id = up.payee_id
    WHERE
        TRUE
        AND up.payee_id IS NULL
        AND p.transfer_account_id IS NULL
        AND p.name != 'Reconciliation Balance Adjustment'
        AND p.name != 'Manual Balance Adjustment'
        AND NOT p.deleted
        AND p.plan_id = :plan_id
    UNION
    SELECT
        plan_id
        , name
    FROM payees
    WHERE
        TRUE
        AND NOT deleted
        AND plan_id = :plan_id
    GROUP BY plan_id, name
    HAVING COUNT(*) > 1
)

SELECT
    p.id AS payee_id
    , p.name AS payee_name
FROM candidates AS c
INNER JOIN
    payees AS p
    ON c.plan_id = p.plan_id AND c.name = p.name AND NOT p.deleted
ORDER BY p.name, p.id
;
