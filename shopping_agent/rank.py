"""Turning Products into ranked Candidates.

The two rules this module exists to hold: a Veto removes a Product entirely
(it does not become a low-ranked Candidate), and anything merely unverifiable
becomes a Warning plus an Unknown dimension score — never an exclusion.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .db import member_age_years
from .preferences import EffectivePreferenceSet
from .recalls import CONFIRMED, RecallMatch
from .scoring import UNKNOWN, DimensionScore, Score
from .search import Product


@dataclass
class Candidate:
    """A Product that survived every Veto and can therefore be ranked."""

    product: Product
    score: Score
    warnings: list[str] = field(default_factory=list)
    recall: RecallMatch | None = None


@dataclass
class Vetoed:
    product: Product
    reason: str
    evidence_url: str = ""


def _budget_score(price: float | None, target: float | None) -> tuple[float | None, str]:
    if price is None:
        return None, "no price given"
    if target is None:
        return None, "no budget set"
    if price <= target:
        return 1.0, f"${price:.2f} within ${target:.2f}"
    over = (price - target) / target
    return max(0.0, 1.0 - over), f"${price:.2f} is {over * 100:.0f}% over ${target:.2f}"


def _avoid_score(text: str, avoided: frozenset[str]) -> tuple[float | None, str]:
    """Avoid-lists are scored, not vetoed — a Preference never removes a Product.

    Only a Blocklist Entry does that, and it is checked before ranking.
    """
    if not avoided:
        return None, "nothing to avoid"
    hits = sorted(a for a in avoided if a in text.lower())
    if hits:
        return 0.0, f"contains avoided: {', '.join(hits)}"
    return 1.0, "none of the avoided terms appear"


def _safety_score(recall: RecallMatch | None) -> tuple[float | None, str]:
    """Absence of a recall is weak evidence of safety, not proof of it.

    A clean CPSC lookup only says this product was not recalled — so it scores
    well but never 1.0, and a Possible match drags it down without vetoing.
    """
    if recall is None:
        return 0.8, "no CPSC recall matched"
    if recall.tier == CONFIRMED:
        return 0.0, "confirmed recall"
    return 0.2, f"possible recall: {recall.why}"


def build_candidate(
    product: Product,
    prefs: EffectivePreferenceSet,
    *,
    recall: RecallMatch | None = None,
    budget: float | None = None,
    member: dict | None = None,
) -> Candidate:
    dimensions: list[DimensionScore] = []
    warnings: list[str] = []
    text = f"{product.title} {product.snippet}"

    for dimension in prefs.dimensions:
        weight = prefs.weight(dimension)
        if dimension == "safety":
            value, reason = _safety_score(recall)
        elif dimension == "budget":
            value, reason = _budget_score(product.representative_price, budget)
        elif dimension in ("brand-avoid", "material-avoid"):
            value, reason = _avoid_score(text, prefs.avoided(dimension))
        else:
            # eco and anything else: a listing title rarely states it, and
            # guessing from marketing words would manufacture evidence.
            value, reason = None, "not stated in the listing"

        dimensions.append(
            DimensionScore(
                dimension=dimension,
                value=UNKNOWN if value is None else value,
                weight=weight,
                reason=reason,
            )
        )
        if value is None:
            warnings.append(f"{dimension}: {reason}")

    if recall is not None and recall.tier != CONFIRMED:
        warnings.insert(0, f"possible recall — {recall.record.title[:70]} ({recall.record.url})")

    age = member_age_years(member) if member else None
    if age is not None and age < 3 and "small parts" in text.lower():
        warnings.append("mentions small parts and the beneficiary is under 3")

    return Candidate(product=product, score=Score(dimensions), warnings=warnings, recall=recall)


def rank(candidates: list[Candidate]) -> list[Candidate]:
    """Highest score first; Products whose Score is Unknown sort last.

    Unknown sorts last rather than as zero because 'we could not assess this'
    is a different claim from 'this assessed badly', and only the ordering can
    say so once the number is gone.
    """
    def key(c: Candidate) -> tuple[int, float]:
        value = c.score.value
        return (0, -float(value)) if value is not UNKNOWN else (1, 0.0)

    return sorted(candidates, key=key)
