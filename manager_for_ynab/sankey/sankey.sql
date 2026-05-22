WITH filtered_transactions AS (
    SELECT
        ft.category_group_id
        , ft.category_group_name
        , ft.category_id
        , ft.category_name
        , ft.amount
        , cg.internal AS category_group_internal
        , COALESCE(ft.payee_name, '') AS payee_name
    FROM flat_transactions AS ft
    LEFT JOIN category_groups AS cg
        ON ft.category_group_id = cg.id
    WHERE
        ft."date" BETWEEN ? AND ?
        AND LOWER(ft.cleared) = 'reconciled'
        AND COALESCE(ft.payee_name, '') != 'Starting Balance'
)

, ready_to_assign_income AS (
    SELECT
        category_group_id
        , category_group_name
        , category_id
        , category_name
        , payee_name
        , SUM(amount) AS amount
    FROM filtered_transactions
    WHERE category_name = 'Inflow: Ready to Assign'
    GROUP BY
        category_group_id
        , category_group_name
        , category_id
        , category_name
        , payee_name
    HAVING SUM(amount) > 0
)

, category_totals AS (
    SELECT
        category_group_id
        , category_group_name
        , category_id
        , category_name
        , category_name AS payee_name
        , SUM(amount) AS amount
    FROM filtered_transactions
    WHERE NOT category_group_internal
    GROUP BY
        category_group_id
        , category_group_name
        , category_id
        , category_name
    HAVING SUM(amount) != 0
)

SELECT
    category_group_id
    , category_group_name
    , category_id
    , category_name
    , payee_name
    , amount
FROM ready_to_assign_income

UNION ALL

SELECT
    category_group_id
    , category_group_name
    , category_id
    , category_name
    , payee_name
    , amount
FROM category_totals

ORDER BY
    category_group_id
    , category_group_name
    , category_id
    , category_name
    , payee_name
;
