# manager-for-ynab

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/mxr/manager-for-ynab/main.svg)](https://results.pre-commit.ci/latest/github/mxr/manager-for-ynab/main)

Manager for YNAB.

## What This Does

This repo is a single CLI for YNAB-focused tools.

- `reconciler`: find and automatically reconciles unreconciled transactions
- `pending-income`: move pending income transactions to today
- `zero-out`: set a category's planned amount to zero across a month range

Tool-specific docs:

- [Reconciler](manager_for_ynab/reconciler/README.md)
- [Pending Income](manager_for_ynab/pending_income/README.md)
- [Zero Out](manager_for_ynab/zero_out/README.md)

## Installation

```console
$ pip install manager-for-ynab
```

## Usage

```console
$ manager-for-ynab --help
$ manager-for-ynab reconciler --help
$ manager-for-ynab pending-income --help
$ manager-for-ynab zero-out --help
```
