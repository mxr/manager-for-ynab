INSERT INTO categories (
    id
    , plan_id
    , deleted
    , category_group_name
    , name
) VALUES
(
    'store-card-category-1'
    , :plan_id
    , 0
    , 'Credit Card Payments'
    , 'Store Card'
)
, (
    'store-card-category-2'
    , :plan_id
    , 0
    , 'Credit Card Payments'
    , 'Store Card'
)
, (
    'groceries-food-category'
    , :plan_id
    , 0
    , 'Food'
    , 'Groceries'
)
, (
    'groceries-household-category'
    , :plan_id
    , 0
    , 'Household'
    , 'Groceries'
)
;
