# Sankey

`manager-for-ynab sankey` draws a Plotly Sankey diagram for reconciled spending in an inclusive date range.

```console
$ manager-for-ynab sankey --start 2026-01-01 --end 2026-01-31
$ manager-for-ynab sankey --start 2026-01-01 --end 2026-01-31 --html
$ manager-for-ynab sankey --start 2026-01-01 --end 2026-01-31 --no-sync
```

By default, the command syncs the local sqlite-export-for-ynab database and calls Plotly's `show()`.
Use `--html` to write `sankey.html` instead.
