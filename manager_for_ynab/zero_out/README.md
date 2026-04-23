# Zero Out

## What This Does

`manager-for-ynab zero-out` zeroes a category's planned amount across a month range. It previews the affected months by default and only updates YNAB when you pass `--for-real`.

Category group and category name lookups use SQL `LIKE` matching. If you do not pass `%` or `_`, the CLI wraps the value in `%...%`, so plain text behaves like a case-insensitive substring match.

## Usage

Set a YNAB personal access token first:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

Preview the months that would be updated:

```console
$ manager-for-ynab zero-out --category-name 'Stuff I Forgot' --start 2025-01 --end 2025-06
```

The command always uses `LIKE`, so this is equivalent to searching for `'%Stuff I Forgot%'`.

If the category name pattern matches more than one category, specify the group too:

```console
$ manager-for-ynab zero-out --category-group 'True Expenses' --category-name 'Stuff I Forgot' --start 2025-01 --end 2025-06
```

You can also pass explicit `LIKE` wildcards:

```console
$ manager-for-ynab zero-out --category-group 'True%' --category-name 'Stuff _ Forgot' --start 2025-01 --end 2025-06
```

Apply the zero-out:

```console
$ manager-for-ynab zero-out --category-group 'True Expenses' --category-name 'Stuff I Forgot' --start 2025-01 --end 2025-06 --for-real
```
