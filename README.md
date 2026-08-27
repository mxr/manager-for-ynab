# manager-for-ynab

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/mxr/manager-for-ynab/main.svg)](https://results.pre-commit.ci/latest/github/mxr/manager-for-ynab/main)

Manager for YNAB.

## What This Does

This repo is a single CLI for YNAB-focused tools.

- `reconciler`: find and automatically reconciles unreconciled transactions
- `auto-approve`: approve matched transactions automatically
- `add-transaction`: create a transaction and optionally fund a category
- `pending-income`: move pending income transactions to today
- `sankey`: draw a Sankey diagram for reconciled spending
- `zero-out`: set a category's planned amount to zero across a month range
- `delete-payees`: delete one or more payees using YNAB's undocumented internal sync API

Tool-specific docs:

- [Reconciler](manager_for_ynab/reconciler/README.md)
- [Auto Approve](manager_for_ynab/auto_approve/README.md)
- [Add Transaction](manager_for_ynab/add_transaction/README.md)
- [Pending Income](manager_for_ynab/pending_income/README.md)
- [Sankey](manager_for_ynab/sankey/README.md)
- [Zero Out](manager_for_ynab/zero_out/README.md)
- [Delete Payees](manager_for_ynab/delete_payees/README.md)

## Installation

```console
$ pip install manager-for-ynab
```

## Usage

```console
$ manager-for-ynab --help
$ manager-for-ynab reconciler --help
$ manager-for-ynab auto-approve --help
$ manager-for-ynab add-transaction --help
$ manager-for-ynab pending-income --help
$ manager-for-ynab sankey --help
$ manager-for-ynab zero-out --help
$ manager-for-ynab delete-payees --help
```
