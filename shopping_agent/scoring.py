"""Dimension scores, the Unknown value, and the Score built from them.

The single rule this module exists to enforce: Unknown is not a low score. It
is excluded from the weighted average entirely, so a Product is never punished
for a merchant's incomplete description. See docs/adr/0002.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The axes a Preference can be expressed on. Order is display order.
DIMENSIONS = (
    "safety", "reliability", "eco", "budget", "brand-avoid", "material-avoid",
)


class _Unknown:
    """Sentinel for a Dimension Score that could not be determined.

    A distinct type rather than None so that `score is UNKNOWN` reads as the
    domain concept, and so an accidental `float(...)` raises instead of
    silently becoming 0.0 — which is the exact error the term exists to prevent.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNKNOWN"

    def __bool__(self) -> bool:  # `if score:` must not treat Unknown as falsy-zero
        raise TypeError("Unknown has no truth value; compare with `is UNKNOWN` instead")


UNKNOWN = _Unknown()


@dataclass(frozen=True)
class DimensionScore:
    """How well a Product satisfies one Dimension: 0..1, or UNKNOWN."""

    dimension: str
    value: float | _Unknown
    weight: float
    reason: str = ""

    @property
    def is_known(self) -> bool:
        return self.value is not UNKNOWN

    def __post_init__(self) -> None:
        if self.is_known and not 0.0 <= float(self.value) <= 1.0:
            raise ValueError(f"{self.dimension} score {self.value!r} outside 0..1")


@dataclass
class Score:
    """A Candidate's standing: the weighted mean of its KNOWN dimension scores."""

    dimensions: list[DimensionScore] = field(default_factory=list)

    @property
    def known(self) -> list[DimensionScore]:
        return [d for d in self.dimensions if d.is_known]

    @property
    def unknown(self) -> list[DimensionScore]:
        return [d for d in self.dimensions if not d.is_known]

    @property
    def value(self) -> float | _Unknown:
        """Weighted mean over known dimensions only.

        Unknown dimensions are absent from both numerator and denominator. With
        nothing known at all the Score is itself UNKNOWN — not 0.0, which would
        rank a product we know nothing about below one we know is bad.
        """
        known = [d for d in self.known if d.weight > 0]
        if not known:
            return UNKNOWN
        total_weight = sum(d.weight for d in known)
        return sum(float(d.value) * d.weight for d in known) / total_weight

    @property
    def evidence_ratio(self) -> str:
        """How much of the weight actually rested on evidence.

        Displayed alongside the Score because a high value over one known
        dimension is not the same claim as the same value over five.
        """
        return f"{len(self.known)}/{len(self.dimensions)}"
