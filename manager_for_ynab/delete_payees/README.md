# Delete Payees

## What This Does

`manager-for-ynab delete-payees` lists unused payees and can delete them (or any payee you specify by ID). YNAB's public API
has no payee-delete endpoint. This command instead calls the same undocumented
`syncBudgetData` sync endpoint (`POST https://app.ynab.com/api/v1/catalog`) that app.ynab.com's web UI uses, marking each payee entity as a tombstone. Because it's an undocumented browser endpoint, it needs your logged-in browser
session to delete unused payees.

With no args, it outputs the unused payees as a table (ID and name). Alternatively you can select specific payees with `--payee-ids`. If you pass `--for-real` it will delete the payees instead of just printing. Payees are deleted in batches of `--batch-size` (default 10) per request.

## Auth

You still need a personal access token for reading data:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

You additionally need two things from a logged-in app.ynab.com browser session:

- **Session cookie**: read automatically from your Firefox cookie jar. You must be
  logged into app.ynab.com in Firefox for this to work.
- **Session token**: Resolved in
  this order:
  1. A previously-captured token cached in the SQLite DB at `--session-token-db`
     (defaults under `$XDG_DATA_HOME` or `~/.local/share`).
  2. Otherwise, installs Playwright's Firefox build if necessary, opens a Playwright-driven Firefox window, seeds it with your
     already-valid session cookie so it loads
     app.ynab.com already logged in, reads the `X-Session-Token` header off the
     first request that carries it, then caches it in `--session-token-db` for next
     time.


Session data is only read when `--for-real` is passed. If the cached session token goes stale then delete the `--session-token-db` file to force recapture.

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
