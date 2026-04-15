# Reconciler

## What This Does

`manager-for-ynab reconciler` finds and automatically reconciles the set of unreconciled YNAB transactions that will bring an account to a target balance. It can either preview the matching transactions or reconcile them through the YNAB API.

## Usage

Set a YNAB personal access token first:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

Preview a single account reconciliation:

```console
$ manager-for-ynab reconciler --account-like 1234 --target 500.30
```

Apply it:

```console
$ manager-for-ynab reconciler --account-like 1234 --target 500.30 --for-real
```

Run batch mode:

```console
$ manager-for-ynab reconciler --mode batch --account-target-pairs 'Checking=500' 'Credit=290' --for-real
```

Bare `--account-like` values are treated as substring matches. Include `%` or `_` yourself when you want explicit SQL `LIKE` wildcard behavior.
