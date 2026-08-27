# Shopping Agent

Finds and ranks products against a household's stated needs, refuses the ones it can prove are
unsafe, and watches prices for the ones worth waiting on. Scoped to this subsystem — this is a
glossary, not a spec.

## Language

### What is being shopped for

**Shopping Request**:
One need the household wants met — "a booster seat for the youngest child", "a cordless drill". The unit that
search, veto, and ranking all operate on. A Shopping Request names a Beneficiary and (optionally) a
Category; those are what decide which Preferences apply. Distinct from the raw text sent to a search
source, which is a mechanical detail of one attempt to satisfy the Request.
_Avoid_: Query, search — those name the mechanism, not the need. A Request can outlive several
queries.

**Beneficiary**:
The Member a Shopping Request is for — the person who will *use* the item, never the person paying.
"A booster seat for the youngest child" makes that child the Beneficiary even though a parent
pays. This is the only
thing that selects Member-level Preferences, so it is required on every Request that should inherit
them.
_Avoid_: Recipient, owner, buyer — all three blur the payer/user distinction that matters here.

**Member**:
A person in the household who can be a Beneficiary and can carry Preferences. Members are created
locally by the household; none ship with this project.
_Avoid_: User — the operator running the tool is not the same as the person the item is for.

**Category**:
A kind of product ("toys", "car seats", "kitchen appliances"). Carries Preferences that apply
family-wide rather than to one person.
_Avoid_: Type, tag.

### Search results

**Product**:
One distinct item, identified by the search source's own product identifier. The search source
returns Products already deduplicated — one row per item, not one per merchant — so a Product's
identity is **given, not inferred**. This is what search, veto, and ranking all operate on.
_Avoid_: Item, SKU, result — "SKU" implies a manufacturer's identifier; this is the search source's
identity for the item, and is only meaningful against that source.

**Listing**:
One named merchant's offer for a Product — the price at one store. A Product records *whether*
several merchants sell it, but the individual Listings are **not** part of a search result and must
be retrieved separately, at cost, for a Product already of interest. A Product therefore routinely
has zero known Listings, and that is the normal case rather than missing data.
_Avoid_: Offer, seller, price — "price" alone hides the question that matters: *whose* price.

**Representative Price**:
The single price the search source attaches to a Product, drawn from one merchant of its choosing. It
is **not** the lowest price across merchants and must never be shown as one; establishing the
cheapest offer means retrieving that Product's Listings. Every price on a Product is a Representative
Price until Listings prove otherwise.
_Avoid_: Best price, lowest price, cheapest — each asserts a comparison that has not been made.

**Candidate**:
A Product that survived every Veto and is therefore eligible to be Ranked. The distinction from
Product matters because a vetoed Product is not a low-ranked Candidate — it is not a Candidate at
all, and never appears in a ranking.
_Avoid_: Result, option.

### Preferences and how they bind

**Preference**:
A stored, weighted statement of what the household cares about on one Dimension, carrying the
household's own wording alongside the structured form. A Preference **only ever influences ranking**;
it can never remove a Product. Anything with the power to remove is a Constraint (below).
_Avoid_: Rule, requirement, filter — all three imply exclusion power that a Preference does not have.

**Dimension**:
One axis a Preference is expressed on: safety, reliability, eco, budget, brand-avoid,
material-avoid. Each Dimension is scored independently and reported independently. A Dimension only
earns its place if it can actually be scored from available evidence some of the time — one that
would always be Unknown adds noise to every result while telling the household nothing.
_Avoid_: Criterion, factor, feature.

**Preference Scope**:
Whether a Preference attaches to a Member (applies to everything bought for that person) or to a
Category (applies family-wide for that kind of product). The two levels are independent; neither is a
special case of the other.

**Effective Preference Set**:
The Preferences actually in force for one Shopping Request, produced by merging the Beneficiary's
Member-level Preferences with the Request's Category-level Preferences. Where both speak to the same
Dimension, **the stricter side wins**: the higher weight is kept, and avoid-lists are unioned rather
than replaced. Merging never weakens a stated preference.
_Avoid_: Combined/final preferences — "effective" is the point: it exists only for the duration of
one Request and is never stored.

**Constraint**:
The umbrella for anything that narrows results, covering both enforcement tiers. Useful only when
speaking about both at once; in almost every other sentence the precise tier — Veto or Preference —
is the right word.

### The two enforcement tiers

**Veto**:
Absolute exclusion of a Product from the results. A Veto has exactly two legitimate sources: a
Confirmed Recall Match, or a Blocklist Entry. **Nothing else may veto** — in particular, absent or
unreadable information never vetoes, because "we could not tell" is not evidence of harm.
_Avoid_: Filter, block, reject — "filter" is used loosely for ranking elsewhere and blurs the line
this term is drawn to protect.

**Blocklist Entry**:
A brand or merchant the household has decided to refuse outright. Human-authored and absolute, which
is what earns it Veto power — unlike a Recall Match, it involves no inference.
_Avoid_: Banned, blacklist.

**Warning**:
A prominent caution attached to a Product that does **not** remove it, always carrying a link to the
underlying evidence so a person can settle the question themselves in seconds. The response to
uncertainty is a Warning; the response to proof is a Veto.
_Avoid_: Flag, note, alert — "alert" belongs to price Notification.

### Recall evidence

**Recall Record**:
One published product-recall entry from the safety authority, including the hazard described. The
authoritative input to the Veto tier — the only external source trusted to remove a Product.

**Recall Match**:
An association drawn between a Product and a Recall Record. Because both sides are free text with no
shared identifier, every Recall Match carries a confidence tier, and the tier decides the
consequence. A Recall Match is never reported without its tier.

**Confirmed Recall Match**:
A Recall Match strong enough to act on alone — the brand matches exactly *and* the product type
agrees. Produces a Veto, reported with the hazard and a link to the Recall Record.

**Possible Recall Match**:
A Recall Match resting on weaker evidence — brand alone, or title similarity alone. Produces a
Warning, never a Veto. The reasoning: a safe product silently removed is invisible to the household
and cannot be argued with, whereas a real recall shown as a warning still reaches them. A heuristic
is not permitted to masquerade as a verified fact.

### Scoring

**Dimension Score**:
How well a Product satisfies one Dimension: a value from 0 to 1, **or Unknown**.

**Unknown**:
A first-class Dimension Score meaning the information needed was not available — explicitly **not**
zero and explicitly **not** "satisfied". Unknown is excluded from the Score's denominator, so a
Product is never punished for a merchant's incomplete listing, and it is always rendered as Unknown
in output so that missing evidence is never mistaken for a passing grade.
_Avoid_: N/A, null, 0 — writing it as zero is precisely the error this term exists to prevent.

**Score**:
A Candidate's overall standing for one Shopping Request: the weighted average of its **known**
Dimension Scores. Never presented alone — the per-Dimension breakdown, including which Dimensions
were Unknown, is shown with it, so a ranking can always be interrogated rather than trusted.
_Avoid_: Rating, grade, confidence — "rating" collides with merchant star ratings.

### Watching a price

**Watch**:
A standing instruction to keep observing the price for a Shopping Request, paired with a Target
Price. A Watch persists until removed; the Shopping Request that created it does not.
_Avoid_: Alert, subscription, tracker.

**Target Price**:
The threshold on a Watch below which the household wants to be told. Chosen by a person; never
inferred.

**Snapshot**:
One observation of a Watch's price at one moment, recorded on **every** check whether or not anything
changed, so that the record has no gaps. Append-only: a Snapshot is never revised.
_Avoid_: Reading, sample, price point.

**Price History**:
The ordered series of Snapshots this project has itself collected for a Watch. **Forward-only** — it
begins the day the Watch is created and can say nothing about prices before that. Deliberately
distinct from any third-party retrospective price history, which this project does not have; the two
must never be presented as the same thing.
_Avoid_: Price chart, historical prices — both invite the assumption of backfilled data that does not
exist.

**Crossing**:
The first Snapshot at or below a Watch's Target Price. A Crossing is what earns a Notification;
subsequent Snapshots that remain below the target are not Crossings and are not announced again.
_Avoid_: Hit, trigger, drop — a "drop" is any decrease, most of which are not Crossings.

**Notification**:
The one message sent to the household when a Crossing occurs. Deliberately rare: a message sent on
every check is noise that gets ignored, which would defeat the Watch entirely.
_Avoid_: Alert, reminder.
