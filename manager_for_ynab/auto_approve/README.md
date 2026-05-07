# Auto Approve

## What This Does

`manager-for-ynab auto-approve` finds transactions that can be updated without manual review:

- matched transaction pairs where both sides are unapproved and undeleted
- unapproved transactions that match a scheduled transaction one month later

For matched pairs, it mirrors the YNAB UI behavior: if one side has an `import_payee_name` value that is a JSON object, that row is deleted and the other row is approved. Otherwise, matching rows are approved. Scheduled transaction matches are approved.

Preview mode prints each transaction with an action of `Update` or `Delete`. Applying changes runs the YNAB API requests concurrently, limited to five requests at a time.

## Usage

Set a YNAB personal access token first:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

Preview the transactions that would be updated:

```console
$ manager-for-ynab auto-approve
```

Apply the updates:

```console
$ manager-for-ynab auto-approve --for-real
```

By default, the command refreshes the local sqlite-export-for-ynab database before reading from it. Pass `--no-sync` to use the existing database contents without syncing.
