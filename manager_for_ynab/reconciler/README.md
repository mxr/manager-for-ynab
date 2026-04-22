# Reconciler

## What This Does

When YNAB imports your transactions and balances stay in sync, reconciliation is straightforward. When they do not, finding the right set of transactions to clear can be tedious. `manager-for-ynab reconciler` finds the unreconciled YNAB transactions that bring an account to a target balance, then either prints them or reconciles them through the YNAB API.

Suppose you want to reconcile a credit card account ending in `1234` to `$1,471.32`:

```console
$ manager-for-ynab reconciler --account-like 1234 --target 1471.32 --for-real
```

By default, bare `--account-like` values are wrapped in `%...%`, so `1234` behaves like a substring match. If you want explicit SQL `LIKE` behavior, include `%` or `_` yourself.

## Usage

### Token

Provision a [YNAB Personal Access Token](https://api.ynab.com/#personal-access-tokens) and save it as an environment variable.

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

### Quickstart

Preview the transactions that would be reconciled:

```console
$ manager-for-ynab reconciler --account-like 1234 --target 500.30
```

Run it again with `--for-real` to reconcile the account:

```console
$ manager-for-ynab reconciler --account-like 1234 --target 500.30 --for-real
```

Process multiple accounts in one run with batch mode:

```console
$ manager-for-ynab reconciler --mode batch --account-target-pairs 'Checking%=500' 'Credit%=290' --for-real
```

Prompt for the targets interactively with interactive batch mode:

```console
$ manager-for-ynab reconciler --mode interactive-batch --account-likes Checking "Credit Card" --for-real
Target balances in matching order, separated by spaces: 500 290
```

`--account-likes` uses the same matching rules as `--account-like`: plain text is normalized to a substring match, while `%` and `_` keep their usual SQL `LIKE` meaning.

### All Options

```console
$ manager-for-ynab reconciler --help
usage: manager-for-ynab reconciler [-h]
                                   [--mode {single,batch,interactive-batch}]
                                   [--account-like ACCOUNT_LIKE]
                                   [--account-likes ACCOUNT_LIKES [ACCOUNT_LIKES ...]]
                                   [--target TARGET]
                                   [--account-target-pairs ACCOUNT_TARGET_PAIRS [ACCOUNT_TARGET_PAIRS ...]]
                                   [--for-real]
                                   [--sqlite-export-for-ynab-db SQLITE_EXPORT_FOR_YNAB_DB]
                                   [--sqlite-export-for-ynab-full-refresh]

Find and automatically reconciles unreconciled transactions.

options:
  -h, --help            show this help message and exit
  --mode {single,batch,interactive-batch}
                        Reconciliation mode. `single` uses --account-
                        like/--target. `batch` uses --account-target-pairs.
                        `interactive-batch` uses --account-likes and prompts
                        for targets.
  --account-like ACCOUNT_LIKE
                        SQL LIKE pattern to match account name (must match
                        exactly one account)
  --account-likes ACCOUNT_LIKES [ACCOUNT_LIKES ...]
                        Interactive batch mode only. Space-separated SQL LIKE
                        patterns to match account names before prompting for
                        target balances.
  --target TARGET       Target balance to match towards for reconciliation
  --account-target-pairs ACCOUNT_TARGET_PAIRS [ACCOUNT_TARGET_PAIRS ...]
                        Batch mode only. Account pattern/target pairs in
                        `ACCOUNT_LIKE=TARGET` format (example:
                        `Checking%=500.30`).
  --for-real            Whether to actually perform the reconciliation. If
                        unset, this tool only prints the transactions that
                        would be reconciled.
  --sqlite-export-for-ynab-db SQLITE_EXPORT_FOR_YNAB_DB
                        Path to sqlite-export-for-ynab SQLite DB file
                        (respects sqlite-export-for-ynab configuration; if
                        unset, will be $HOME/.local/share/sqlite-export-for-
                        ynab/db.sqlite)
  --sqlite-export-for-ynab-full-refresh
                        Whether to **DROP ALL TABLES** and fetch all plan data
                        again. If unset, this tool only does an incremental
                        refresh
```
