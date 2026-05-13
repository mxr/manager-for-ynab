SELECT
    category_group_name
    , category_name
    , SUM(amount) AS amount
FROM flat_transactions
WHERE
    "date" BETWEEN ? AND ?
    AND LOWER(cleared) = 'reconciled'
    AND COALESCE(payee_name, '') != 'Starting Balance'
    AND category_group_name != 'Internal Master Category'
GROUP BY
    category_group_name
    , category_name
;
