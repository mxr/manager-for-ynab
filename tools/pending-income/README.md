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

Preview the same result as JSON:

```console
$ manager-for-ynab pending-income --json
```

Apply the date updates:

```console
$ manager-for-ynab pending-income --for-real
```

Apply the date updates and emit JSON with the transactions and updated count:

```console
$ manager-for-ynab pending-income --for-real --json
```
