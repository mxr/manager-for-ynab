# Pending Transaction

## What This Does

`manager-for-ynab pending-transaction` finds uncleared transactions dated before today in the current month and moves
them to today. It picks up positive transactions in any account, and transactions of either sign in checking accounts
that are not linked for direct import (for example, a cash wallet). By default it only previews the transactions it
found.

## Usage

Set a YNAB personal access token first:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

Preview the pending transactions:

```console
$ manager-for-ynab pending-transaction
```

Apply the date updates:

```console
$ manager-for-ynab pending-transaction --for-real
```

Exclude already matched transactions (to avoid changing the date once YNAB picks up the transaction):

```console
$ manager-for-ynab pending-transaction --skip-matched
```

By default, the command refreshes the local sqlite-export-for-ynab database before reading from it. Pass `--no-sync` to
use the existing database contents without syncing.
