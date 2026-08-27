# shopping-agent

Searches and ranks products against a household's stated needs, refuses the ones it can prove are
unsafe, and watches prices for the ones worth waiting on.

Read [`CONTEXT.md`](CONTEXT.md) before changing behaviour — it is the source of truth for what the
terms mean, and several of them are drawn deliberately narrowly (a `Representative Price` is *not* a
lowest price; `Unknown` is *not* a low score; a `Preference` can never remove a product).

## What it does

- **Search & rank** — finds products for a need, scores them against the preferences stored for
  whoever the item is *for*, and shows the per-dimension breakdown so a ranking can be interrogated
  rather than trusted.
- **Safety veto** — checks candidates against the U.S. CPSC recall database. A confident match is
  excluded outright; a weaker match is surfaced as a warning with a link, never silently dropped
  (see [`docs/adr/0001`](docs/adr/0001-confidence-tiered-recall-matching.md)).
- **Price watching** — records a snapshot per check and notifies once, on the first crossing below
  your target price.

## Setup

```bash
uv sync --extra dev --extra gui
export SERPAPI_KEY=...        # required for search; free tier is 250 searches/month
```

The CPSC recall API needs no key.

## Usage

```bash
shopping-agent add-member alex --birthdate 2019-04-11
shopping-agent prefer --member alex --dimension safety --weight 3 --note "safety first"
shopping-agent prefer --category toys --dimension eco --weight 2

shopping-agent search "toddler booster seat" --for alex
shopping-agent watch "toddler booster seat" --target 25
shopping-agent check-watches
shopping-agent quota
```

Or use the desktop UI, which drives the same code:

```bash
shopping-agent-gui
```

It shows the per-dimension breakdown behind every score, renders an unscored
dimension as `?` rather than a number, and labels prices as coming from one
merchant rather than as the lowest available.

## Household data stays local

`preferences.db` holds member names, birthdates, and per-child safety needs. It is gitignored and no
member data ships with this project — see
[`docs/adr/0003`](docs/adr/0003-public-repo-private-preference-store.md).

## License

MIT — see `LICENSE`.
