# Pending Income

## What This Does

`manager-for-ynab pending-income` finds uncleared positive transactions dated before today in the current month and moves them to today. By default it only previews the transactions it found.

## Usage

Set a YNAB personal access token first:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

Preview the pending income transactions:

```console
$ manager-for-ynab pending-income
```

Apply the date updates:

```console
$ manager-for-ynab pending-income --for-real
```

Exclude already matched transactions (to avoid changing the date once YNAB picks up the transaction):

```console
$ manager-for-ynab pending-income --skip-matched
```
