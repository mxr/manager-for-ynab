CREATE TABLE flat_transactions (
    category_group_id TEXT
    , category_group_name TEXT
    , category_id TEXT
    , category_name TEXT
    , amount INT
    , cleared TEXT
    , "date" TEXT
    , payee_name TEXT
    , internal BOOLEAN
)
;

INSERT INTO flat_transactions VALUES
(
    'internal-group'
    , 'Internal Master Category'
    , 'ready-to-assign'
    , 'Inflow: Ready to Assign'
    , 500000
    , 'reconciled'
    , '2026-04-01'
    , 'Employer'
    , TRUE
)
, (
    'bills-group'
    , 'Bills'
    , 'rent'
    , 'Rent'
    , -120000
    , 'reconciled'
    , '2026-04-02'
    , 'Landlord'
    , FALSE
)
, (
    'food-group'
    , 'Food'
    , 'groceries'
    , 'Groceries'
    , -45500
    , 'Reconciled'
    , '2026-04-03'
    , 'Market'
    , FALSE
)
, (
    'food-group'
    , 'Food'
    , 'restaurants'
    , 'Restaurants'
    , -20000
    , 'cleared'
    , '2026-04-03'
    , 'Cafe'
    , FALSE
)
, (
    'gifts-group'
    , 'Gifts'
    , 'gifts'
    , 'Gifts'
    , 100000
    , 'reconciled'
    , '2026-04-03'
    , 'Maria Oculam'
    , FALSE
)
, (
    'gifts-group'
    , 'Gifts'
    , 'gifts'
    , 'Gifts'
    , -40000
    , 'reconciled'
    , '2026-04-04'
    , 'Gift Shop'
    , FALSE
)
, (
    'internal-group'
    , 'Internal Master Category'
    , 'hidden'
    , 'Hidden'
    , -10000
    , 'reconciled'
    , '2026-04-03'
    , 'Hidden'
    , TRUE
)
, (
    'bills-group'
    , 'Bills'
    , 'rent'
    , 'Rent'
    , -10000
    , 'reconciled'
    , '2026-05-01'
    , 'Landlord'
    , FALSE
)
, (
    'inflow-group'
    , 'Inflow'
    , 'ready-to-assign'
    , 'Inflow: Ready to Assign'
    , 100000
    , 'reconciled'
    , '2026-04-04'
    , 'Starting Balance'
    , TRUE
)
;
