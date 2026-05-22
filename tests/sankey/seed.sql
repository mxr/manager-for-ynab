INSERT INTO plans (id, name) VALUES ('plan-1', 'My Plan');

INSERT INTO category_groups (id, plan_id, name, internal) VALUES
('internal-group', 'plan-1', 'Internal Master Category', 1)
, ('bills-group', 'plan-1', 'Bills', 0)
, ('food-group', 'plan-1', 'Food', 0)
, ('gifts-group', 'plan-1', 'Gifts', 0)
, ('inflow-group', 'plan-1', 'Inflow', 1)
;

INSERT INTO categories (
    id, plan_id, category_group_id, category_group_name, name, internal
) VALUES
(
    'ready-to-assign'
    , 'plan-1'
    , 'internal-group'
    , 'Internal Master Category'
    , 'Inflow: Ready to Assign'
    , 1
)
, (
    'rent'
    , 'plan-1'
    , 'bills-group'
    , 'Bills'
    , 'Rent'
    , 0
)
, (
    'groceries'
    , 'plan-1'
    , 'food-group'
    , 'Food'
    , 'Groceries'
    , 0
)
, (
    'restaurants'
    , 'plan-1'
    , 'food-group'
    , 'Food'
    , 'Restaurants'
    , 0
)
, (
    'gifts'
    , 'plan-1'
    , 'gifts-group'
    , 'Gifts'
    , 'Gifts'
    , 0
)
, (
    'hidden'
    , 'plan-1'
    , 'internal-group'
    , 'Internal Master Category'
    , 'Hidden'
    , 1
)
, (
    'inflow-ready-to-assign'
    , 'plan-1'
    , 'inflow-group'
    , 'Inflow'
    , 'Inflow: Ready to Assign'
    , 1
)
;

INSERT INTO transactions (
    id
    , plan_id
    , category_id
    , category_name
    , amount
    , cleared
    , "date"
    , payee_name
    , approved
    , deleted
) VALUES
(
    't-employer'
    , 'plan-1'
    , 'ready-to-assign'
    , 'Inflow: Ready to Assign'
    , 500000
    , 'reconciled'
    , '2026-04-01'
    , 'Employer'
    , 1
    , 0
)
, (
    't-rent-april'
    , 'plan-1'
    , 'rent'
    , 'Rent'
    , -120000
    , 'reconciled'
    , '2026-04-02'
    , 'Landlord'
    , 1
    , 0
)
, (
    't-groceries'
    , 'plan-1'
    , 'groceries'
    , 'Groceries'
    , -45500
    , 'Reconciled'
    , '2026-04-03'
    , 'Market'
    , 1
    , 0
)
, (
    't-restaurants'
    , 'plan-1'
    , 'restaurants'
    , 'Restaurants'
    , -20000
    , 'cleared'
    , '2026-04-03'
    , 'Cafe'
    , 1
    , 0
)
, (
    't-gifts-in'
    , 'plan-1'
    , 'gifts'
    , 'Gifts'
    , 100000
    , 'reconciled'
    , '2026-04-03'
    , 'Maria Oculam'
    , 1
    , 0
)
, (
    't-gifts-out'
    , 'plan-1'
    , 'gifts'
    , 'Gifts'
    , -40000
    , 'reconciled'
    , '2026-04-04'
    , 'Gift Shop'
    , 1
    , 0
)
, (
    't-hidden'
    , 'plan-1'
    , 'hidden'
    , 'Hidden'
    , -10000
    , 'reconciled'
    , '2026-04-03'
    , 'Hidden'
    , 1
    , 0
)
, (
    't-rent-may'
    , 'plan-1'
    , 'rent'
    , 'Rent'
    , -10000
    , 'reconciled'
    , '2026-05-01'
    , 'Landlord'
    , 1
    , 0
)
, (
    't-starting-balance'
    , 'plan-1'
    , 'inflow-ready-to-assign'
    , 'Inflow: Ready to Assign'
    , 100000
    , 'reconciled'
    , '2026-04-04'
    , 'Starting Balance'
    , 1
    , 0
)
;
