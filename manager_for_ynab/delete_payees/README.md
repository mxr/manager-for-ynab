# Delete Payees

## What This Does

`manager-for-ynab delete-payees` lists unused payees and can delete them (or any payee you specify by ID). YNAB's public
API has no payee-delete endpoint. This command instead calls the same undocumented `syncBudgetData` sync endpoint
(`POST https://app.ynab.com/api/v1/catalog`) that app.ynab.com's web UI uses, marking each payee entity as a tombstone.
Because it's an undocumented browser endpoint, it needs your logged-in browser session to delete unused payees.

With no args, it outputs the unused payees as a table (ID and name). "Unused" means payees that aren't referenced by any
transaction, subtransaction, scheduled transaction, or scheduled subtransaction, but excludes transfer payees and
balance-adjustment payees. Alternatively you can select specific payees with `--payee-ids`. If you pass `--for-real` it
will delete the payees instead of just printing. Payees are deleted in batches of `--batch-size` (default 10) per
request.

## Auth

Like other tools you will need a personal access token for reading data:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

You will also need a logged-in app.ynab.com browser session for interacting with the undocumented API. The session
cookie and `X-Session-Token` are resolved in this order:

1. A previously-captured cookie and token cached in the SQLite DB at `--session-token-db` (defaults under
   `$XDG_DATA_HOME` or `~/.local/share`).
2. Otherwise, installs Playwright's Firefox build if necessary and opens it with a dedicated browser profile kept in a
   `browser-profile` directory next to `--session-token-db`. Log into app.ynab.com in that window the first time; later
   captures reuse the saved login. It reads the `X-Session-Token` header off the first request that carries it and the
   `_ynab_api_session` cookie from the profile, then caches both in `--session-token-db` for next time.

The dedicated profile is separate from your own browser, so no permission to read another app's data is needed.

Session data is only read when `--for-real` is passed. If the cached session goes stale then delete the
`--session-token-db` file to force recapture. Delete the `browser-profile` directory too to log in again from scratch.

Playwright is an optional dependency (the `delete-payees` extra) since it's only needed for `--for-real`. Install with:

```console
$ pip install manager-for-ynab[delete-payees]
```

## Usage

Preview all unused payees in the plan:

```console
$ manager-for-ynab delete-payees
```

Preview a specific payee:

```console
$ manager-for-ynab delete-payees --payee-ids <payee-id>
```

Delete more than one at once:

```console
$ manager-for-ynab delete-payees --payee-ids <payee-id-1> --payee-ids <payee-id-2>
```

If you have more than one plan, specify which one:

```console
$ manager-for-ynab delete-payees --plan-id <plan-id>
```

Delete for real:

```console
$ manager-for-ynab delete-payees --for-real
```
