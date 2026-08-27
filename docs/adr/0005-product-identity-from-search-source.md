# Product identity comes from the search source, not from matching titles

The search source returns results already deduplicated — one row per item, each carrying its own
product identifier, with a flag indicating whether other merchants also sell it. Product identity is
therefore taken directly from that identifier rather than reconstructed by comparing titles.

This is worth recording because a sibling project in this fleet does the opposite: it receives raw
per-merchant rows and groups them with a title-similarity heuristic. Reading the two side by side, it
would be reasonable to assume this project simply forgot to do the same. It did not — the input shape
is different, and inferring identity that the source already states would add a source of error
without adding information.

## Consequences

Product identity is only meaningful against the source that issued it: identifiers are not portable,
so adding a second search source later means deciding how the two identity spaces relate, and that
decision is deferred rather than solved. In exchange, no heuristic grouping code exists to be tuned,
audited, or explained.

The corollary is that per-merchant prices are no longer free. Because results arrive pre-grouped, the
individual merchant offers behind a Product are a separate, billed retrieval — which is why the price
carried on a Product is a Representative Price and not a lowest price.
