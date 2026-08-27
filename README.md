# shopping-agent

Searches and ranks products against a household's stated needs, refuses the ones it can prove are
unsafe, and watches prices for the ones worth waiting on.

Read [`CONTEXT.md`](CONTEXT.md) before changing behaviour — it is the source of truth for what the
terms mean, and several of them are drawn deliberately narrowly (a `Representative Price` is *not* a
lowest price; `Unknown` is *not* a low score; a `Preference` can never remove a product).

## What it does

- **Search & rank** — finds products for a need, scores them against the preferences stored for
  whoever the item is *for*, and shows the per-dimension breakdown so a ranking can be interrogated
  rather than trusted. Works for anything the household buys: a child's toy is ranked on safety and
  materials, a power tool on reliability and price, because the dimensions that apply come from the
  preferences rather than being fixed.
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
shopping-agent prefer --category electronics --dimension reliability --weight 3

shopping-agent search "toddler booster seat" --for alex --category toys
shopping-agent search "cordless drill" --category electronics --budget 120
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

## Dimensions

`safety`, `reliability`, `eco`, `budget`, `brand-avoid`, `material-avoid`.

Which ones apply is decided by the preferences in force, not by the product — so the same command
serves a car seat and a dishwasher. `reliability` is derived from the merchant rating, but only once
enough people have rated the item; below that it is Unknown rather than a high score, because a
five-star average over three ratings is not evidence.

A dimension only earns its place if it can be scored from available data at least some of the time.
One that is always Unknown would add a column to every result while telling you nothing.

## Household data stays local

`preferences.db` holds member names, birthdates, and per-child safety needs. It is gitignored and no
member data ships with this project — see
[`docs/adr/0003`](docs/adr/0003-public-repo-private-preference-store.md).

## License

MIT — see `LICENSE`.
