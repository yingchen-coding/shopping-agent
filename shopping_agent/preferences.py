"""Preferences and the Effective Preference Set.

Member-level and Category-level Preferences are independent stores; neither is a
special case of the other. Merging them for one Shopping Request must never
weaken a stated preference — see the Effective Preference Set entry in CONTEXT.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .scoring import DIMENSIONS


@dataclass(frozen=True)
class Preference:
    """A weighted statement about one Dimension, plus the household's own words.

    A Preference only ever influences ranking. It can never remove a Product;
    that power belongs to a Veto alone.
    """

    dimension: str
    weight: float
    note: str = ""
    avoid: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSIONS:
            raise ValueError(f"unknown dimension {self.dimension!r}; expected one of {DIMENSIONS}")
        if self.weight < 0:
            raise ValueError("weight cannot be negative")


@dataclass
class EffectivePreferenceSet:
    """The Preferences in force for one Shopping Request.

    Exists only for the duration of that Request and is never stored.
    """

    by_dimension: dict[str, Preference] = field(default_factory=dict)
    sources: dict[str, list[str]] = field(default_factory=dict)

    def weight(self, dimension: str) -> float:
        pref = self.by_dimension.get(dimension)
        return pref.weight if pref else 0.0

    def avoided(self, dimension: str) -> frozenset[str]:
        pref = self.by_dimension.get(dimension)
        return pref.avoid if pref else frozenset()

    @property
    def dimensions(self) -> list[str]:
        return [d for d in DIMENSIONS if d in self.by_dimension]


def merge(
    member_prefs: list[Preference],
    category_prefs: list[Preference],
) -> EffectivePreferenceSet:
    """Combine the two levels, stricter side winning on every conflict.

    Stricter means: the higher weight is kept, and avoid-lists are unioned
    rather than replaced. Union rather than override is the point — a brand the
    household avoids for toys generally is still avoided when buying for one
    child, even if that child's own preferences never mention it.
    """
    effective = EffectivePreferenceSet()

    for level, prefs in (("member", member_prefs), ("category", category_prefs)):
        for pref in prefs:
            existing = effective.by_dimension.get(pref.dimension)
            effective.sources.setdefault(pref.dimension, []).append(level)
            if existing is None:
                effective.by_dimension[pref.dimension] = pref
                continue
            notes = [n for n in (existing.note, pref.note) if n]
            effective.by_dimension[pref.dimension] = Preference(
                dimension=pref.dimension,
                weight=max(existing.weight, pref.weight),
                note=" / ".join(notes),
                avoid=existing.avoid | pref.avoid,
            )
    return effective
