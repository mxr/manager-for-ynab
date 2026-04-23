# Zero Out

## What This Does

`manager-for-ynab zero-out` zeroes a category's planned amount across a month range. It previews the affected months by default and only updates YNAB when you pass `--for-real`.

Category lookup matches by category name, with an optional `--category-group` to disambiguate duplicate names across groups.

## Usage

Set a YNAB personal access token first:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

Preview the months that would be updated:

```console
$ manager-for-ynab zero-out --category-name 'Stuff I Forgot' --start 2025-01 --end 2025-06
```

If the category name exists in more than one group, specify the group too:

```console
$ manager-for-ynab zero-out --category-group 'True Expenses' --category-name 'Stuff I Forgot' --start 2025-01 --end 2025-06
```

Apply the zero-out:

```console
$ manager-for-ynab zero-out --category-group 'True Expenses' --category-name 'Stuff I Forgot' --start 2025-01 --end 2025-06 --for-real
```
