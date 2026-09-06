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

It previews the matched payees as a table (ID and name) by default and only deletes
when you pass `--for-real`.

`--payee-ids` targets a specific payee by ID and can be repeated to delete several
payees in one run. If omitted, it finds all unused payee IDs in the plan instead:
payees with no approved transaction, scheduled transaction, or subtransaction, plus
transfer payees and duplicate-named payees.

## Auth

You still need a personal access token for reading data:

```console
$ export YNAB_PERSONAL_ACCESS_TOKEN="..."
```

You additionally need two things from a logged-in app.ynab.com browser session:

- **Session cookie**: read automatically from your Firefox cookie jar. You must be
  logged into app.ynab.com in Firefox for this to work.
- **Session token**: not stored as a cookie, so it can't be read automatically. Set
  `YNAB_SESSION_TOKEN` to the `X-Session-Token` request header value from any XHR
  request to `/api/v1/catalog` (browser devtools -> Network tab).

```console
$ export YNAB_SESSION_TOKEN="..."
```

Both are only read when `--for-real` is passed, so a dry-run preview works with just
the personal access token.

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
