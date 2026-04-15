# manager-for-ynab

[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/mxr/manager-for-ynab/main.svg)](https://results.pre-commit.ci/latest/github/mxr/manager-for-ynab/main)

Manager for YNAB.

## What This Does

This repo is a single CLI for YNAB-focused tools.

- `reconciler`: find unreconciled transactions that match a target balance
- `pending-income`: move pending income transactions to today

Tool-specific docs:

- [Reconciler](tools/reconciler/README.md)
- [Pending Income](tools/pending-income/README.md)

## Installation

```console
$ pip install manager-for-ynab
```

## Usage

```console
$ manager-for-ynab --help
$ manager-for-ynab reconciler --help
$ manager-for-ynab pending-income --help
```
