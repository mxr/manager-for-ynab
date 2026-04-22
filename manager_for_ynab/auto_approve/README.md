# Auto Approve

## What This Does

`manager-for-ynab auto-approve` finds matched transactions that are still unapproved and approves them. It treats a YNAB match as one logical transaction in preview mode, then approves both linked rows when applying changes.

## Usage

Set a YNAB personal access token first:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

Preview the matched transactions that would be approved:

```console
$ manager-for-ynab auto-approve
```

Apply the approval updates:

```console
$ manager-for-ynab auto-approve --for-real
```
