# Product data comes from documented APIs, not anti-detection scraping

The reference project this design borrowed from collects product data partly through a stealth
browser driven over residential IP addresses — an approach whose purpose is to defeat the bot
detection sites deploy to enforce their own terms. This project does not do that, and does not model
it. Product data comes from a documented commercial search API, and recall data from the safety
authority's public endpoint, which needs no authentication at all.

Circumventing access controls is the part that is refused, not scraping in general: reading a page a
site serves willingly is a different act from engineering around its refusal to serve you.

## Consequences

Coverage is narrower and costs more. Sources that only yield to evasion — chiefly some retailers'
own pages and their review corpora — are simply out of reach, and the paid search API is a real
running expense where scraping would have been free. Both were accepted. If a future data source is
proposed, the question to ask is whether it is served willingly, not whether it can be obtained.
