# Recall matches are confidence-tiered, and only the confident tier vetoes

Recall records and Products share no identifier — both sides are free text — so deciding "is
this Product the recalled one?" is always inference, never lookup. (A Product carries an
identifier from the search source, but the safety authority has never heard of it.) Rather than
veto on any textual match, a match with an exact brand *and* agreeing product type produces a
Veto, while a match resting on brand alone or title similarity alone produces a Warning carrying
a link to the recall record.

The asymmetry is deliberate: a safe product removed by a false positive is **invisible** to the
household — they never learn it existed and cannot argue with the decision — whereas a real recall
shown as a prominent warning still reaches them and takes seconds to confirm. Vetoing on weak
evidence would also let a heuristic present itself as a verified fact, which the Warning tier exists
to prevent.

## Consequences

Some Products will carry a Possible Recall Match that turns out to be unrelated, and the household
has to dismiss it. That noise is accepted as the price of never silently deleting a legitimate
option. If the weak tier ever gets promoted to Veto for convenience, this trade-off is being reversed
and the reasoning above needs revisiting first.
