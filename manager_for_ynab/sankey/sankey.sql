SELECT
    category_group_id
    , category_group_name
    , category_id
    , category_name
    , COALESCE(payee_name, '') AS payee_name
    , SUM(amount) AS amount
FROM flat_transactions
WHERE
    "date" BETWEEN ? AND ?
    AND LOWER(cleared) = 'reconciled'
    AND COALESCE(payee_name, '') != 'Starting Balance'
    AND (
        category_group_name != 'Internal Master Category'
        OR category_name = 'Inflow: Ready to Assign'
    )
GROUP BY
    COALESCE(payee_name, '')
    , category_group_id
    , category_group_name
    , category_id
    , category_name
ORDER BY
    category_group_id
    , category_group_name
    , category_id
    , category_name
    , COALESCE(payee_name, '')
;
