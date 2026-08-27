"""CPSC recall lookup and confidence-tiered matching.

Recall records and Products share no identifier, so every match is inference.
The tier decides the consequence: only a Confirmed match may veto; a Possible
match becomes a Warning carrying the record's link. See docs/adr/0001.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

import requests

RECALL_URL = "https://www.saferproducts.gov/RestWebServices/Recall"

# CPSC rejects the HTTP library's default User-Agent with 403. This states
# truthfully who is calling, which is the opposite of the browser
# impersonation refused in docs/adr/0004 — identifying yourself is what a
# well-behaved client does; the ADR refuses disguising yourself.
USER_AGENT = (
    "shopping-agent/0.1 (+https://github.com/yingchen-coding/shopping-agent)"
)

CONFIRMED = "confirmed"
POSSIBLE = "possible"

# Words that carry no identifying weight when comparing a product to a recall.
_NOISE = {
    "the", "a", "an", "and", "or", "for", "with", "of", "in", "by", "to",
    "kids", "kid", "child", "children", "toddler", "baby", "infant",
    "new", "set", "pack", "piece", "pcs", "size", "color", "colour",
    "recalled", "due", "risk", "hazard", "inc", "llc", "co", "brand",
}


class RecallError(RuntimeError):
    """Raised rather than returning empty — 'the safety check failed' and
    'nothing was recalled' must never look the same."""


@dataclass(frozen=True)
class RecallRecord:
    recall_id: str
    title: str
    date: str
    url: str
    hazards: list[str]
    product_names: list[str]

    @property
    def hazard_summary(self) -> str:
        return "; ".join(h.strip() for h in self.hazards if h.strip())[:300]


@dataclass(frozen=True)
class RecallMatch:
    """An inferred association. Never reported without its tier."""

    record: RecallRecord
    tier: str
    why: str

    @property
    def vetoes(self) -> bool:
        return self.tier == CONFIRMED


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _NOISE}


def fetch_recalls(query: str, *, since_days: int = 3650, timeout: float = 45.0) -> list[RecallRecord]:
    """Recalls whose product name matches `query`. Needs no API key."""
    start = (date.today() - timedelta(days=since_days)).isoformat()
    try:
        resp = requests.get(
            RECALL_URL,
            params={"format": "json", "ProductName": query, "RecallDateStart": start},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RecallError(f"CPSC lookup failed: {exc}") from exc
    if resp.status_code != 200:
        raise RecallError(f"CPSC lookup failed: HTTP {resp.status_code}")
    try:
        rows = resp.json()
    except ValueError as exc:
        raise RecallError(f"CPSC returned unparsable data: {exc}") from exc

    records = []
    for row in rows if isinstance(rows, list) else []:
        records.append(
            RecallRecord(
                recall_id=str(row.get("RecallID") or ""),
                title=row.get("Title") or "",
                date=(row.get("RecallDate") or "")[:10],
                url=row.get("URL") or "",
                hazards=[h.get("Name") or "" for h in (row.get("Hazards") or [])],
                product_names=[p.get("Name") or "" for p in (row.get("Products") or [])],
            )
        )
    return records


def match(product_title: str, brand: str, records: list[RecallRecord]) -> RecallMatch | None:
    """Strongest match for one Product, or None.

    Confirmed requires the brand to appear in the recall *and* the product types
    to overlap. Brand alone, or type overlap alone, is Possible — enough to warn
    a person, never enough to remove the product on its own.
    """
    product_tokens = _tokens(product_title)
    brand = (brand or "").lower().strip()
    best: RecallMatch | None = None

    for record in records:
        haystack = " ".join([record.title, *record.product_names])
        recall_tokens = _tokens(haystack)
        shared = product_tokens & recall_tokens
        brand_hit = bool(brand) and brand in _tokens(haystack)

        if brand_hit and shared - {brand}:
            overlap = ", ".join(sorted(shared - {brand})[:4])
            return RecallMatch(
                record=record,
                tier=CONFIRMED,
                why=f"brand '{brand}' and product type match ({overlap})",
            )

        if best is None:
            if brand_hit:
                best = RecallMatch(record, POSSIBLE, f"brand '{brand}' matches, product type unclear")
            elif len(shared) >= 2:
                best = RecallMatch(
                    record, POSSIBLE,
                    f"title overlap ({', '.join(sorted(shared)[:4])}) but brand does not match",
                )
    return best
