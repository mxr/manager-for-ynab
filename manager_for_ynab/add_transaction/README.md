# Add Transaction

`manager-for-ynab add-transaction` creates a new YNAB transaction from the local sqlite-export database and can optionally fund the category from Ready to Assign.

It works interactively by autocompleting payees, categories etc already in your plan.

Use `--for-real` to create the transaction. Without it, the command only previews the transaction that would be sent.

By default, the command refreshes the local sqlite-export-for-ynab database before reading from it. Pass `--no-sync` to use the existing database contents without syncing.
