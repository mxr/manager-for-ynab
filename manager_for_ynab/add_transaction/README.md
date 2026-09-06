# Add Transaction

`manager-for-ynab add-transaction` creates a new YNAB transaction from the local sqlite-export database and can optionally fund the category from Ready to Assign.

It works interactively by autocompleting payees, categories etc already in your plan.

Pass multiple `--account-name` values (space-separated on one flag, or by repeating the flag) to split one purchase across accounts: each account is drained (up to its current balance) in the order given before moving on to the next. At most one account may be a credit card, and it must be listed last, since it only covers whatever amount is left after the other accounts are drained. If an account fully covers the amount, later accounts are left out of the transaction entirely.

Use `--for-real` to create the transaction(s). Without it, the command only previews the transaction(s) that would be sent. All legs of a split are sent to YNAB together in a single request.

By default, the command refreshes the local sqlite-export-for-ynab database before reading from it. Pass `--no-sync` to use the existing database contents without syncing.
