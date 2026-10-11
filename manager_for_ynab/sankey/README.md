# Sankey

`manager-for-ynab sankey` draws an ECharts Sankey diagram for reconciled spending in an inclusive date range.

```console
$ manager-for-ynab sankey
$ manager-for-ynab sankey --start 2026-01-01 --end 2026-01-31
$ manager-for-ynab sankey --start 2026-01-01 --end today
$ manager-for-ynab sankey --start 2026-01-01 --end 2026-01-31 --out sankey.html
$ manager-for-ynab sankey --start 2026-01-01 --end 2026-01-31 --sort-by amount
$ manager-for-ynab sankey --start 2026-01-01 --end 2026-01-31 --no-sync
$ manager-for-ynab sankey --start 2026-01-01 --end 2026-01-31 --format csv --out sankey.csv
$ manager-for-ynab sankey --start 2026-01-01 --end 2026-01-31 -f json
```

By default, the command syncs the local sqlite-export-for-ynab database, uses 1970-01-01 through today, sorts nodes
alphabetically, and writes ECharts HTML to stdout. `--format csv` and `--format json` instead write one row per link
with `input_type`, `input_name`, `output_type`, `output_name`, and `amount_millis`. The `_type` columns name the node
stage (`payee`, `ready_to_assign`, `income_category`, `net_category_income`, `income`, `category_group`, or `category`),
since different stages can share a name. `amount_millis` is in milliunits like the sqlite-export-for-ynab DB.
