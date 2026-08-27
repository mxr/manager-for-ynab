# Delete Payees

## What This Does

`manager-for-ynab delete-payees` deletes one or more payees. YNAB's public API (the
one `asyncio-for-ynab` talks to, and the one used by every other command in this repo)
has no payee-delete endpoint. This command instead calls the same undocumented
`syncBudgetData` sync endpoint (`POST https://app.ynab.com/api/v1/catalog`) that
app.ynab.com's web UI uses, marking each payee entity as a tombstone.

Because it's an undocumented endpoint, it authenticates with your logged-in browser
session instead of a personal access token, on top of the token still needed to read
your plan/payee data through the public API. The delta sync's device-knowledge counter
is seeded from `last_knowledge_of_server` in the local sqlite-export-for-ynab DB, so run
with `--sync` (the default) at least once first.

It previews the matched payees by default and only deletes when you pass `--for-real`.

`--payee-name` matches an exact payee name (case-insensitive) and can be repeated to
delete several payees in one run.

## Auth

You still need a personal access token for reading data:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

You additionally need two things from a logged-in app.ynab.com browser session:

- **Session cookie**: read automatically from your Firefox cookie jar if you're logged
  into app.ynab.com there. Otherwise, set `YNAB_SESSION_COOKIE` to the full `Cookie`
  header value from a request to app.ynab.com (browser devtools -> Network tab).
- **Session token**: not stored as a cookie, so it can't be read automatically. Set
  `YNAB_SESSION_TOKEN` to the `X-Session-Token` request header value from any XHR
  request to `/api/v1/catalog` (browser devtools -> Network tab).

```console
$ export YNAB_SESSION_COOKIE="..."       # optional if using Firefox
$ export YNAB_SESSION_TOKEN="..."
```

Both are only read when `--for-real` is passed, so a dry-run preview works with just
the personal access token.

## Usage

Preview which payees would be deleted:

```console
$ manager-for-ynab delete-payees --payee-name 'Amazon Duplicate'
```

Delete more than one at once:

```console
$ manager-for-ynab delete-payees --payee-name 'Amazon Duplicate' --payee-name 'Old Landlord'
```

If you have more than one plan, specify which one:

```console
$ manager-for-ynab delete-payees --plan-id <plan-id> --payee-name 'Amazon Duplicate'
```

Delete for real:

```console
$ manager-for-ynab delete-payees --payee-name 'Amazon Duplicate' --for-real
```
