import pytest

from shopping_agent.scoring import UNKNOWN, DimensionScore, Score


def test_unknown_is_not_zero_and_is_excluded_from_the_denominator():
    """The rule from docs/adr/0002. If Unknown were scored 0, this would be 0.5."""
    score = Score([
        DimensionScore("safety", 1.0, weight=1),
        DimensionScore("eco", UNKNOWN, weight=1),
    ])
    assert score.value == 1.0
    assert score.evidence_ratio == "1/2"


def test_unknown_weight_does_not_dilute_a_known_score():
    heavy_unknown = Score([
        DimensionScore("safety", 0.8, weight=1),
        DimensionScore("eco", UNKNOWN, weight=99),
    ])
    assert heavy_unknown.value == pytest.approx(0.8)


def test_score_is_unknown_not_zero_when_nothing_is_known():
    """A product we know nothing about must not rank below one known to be bad."""
    assert Score([DimensionScore("eco", UNKNOWN, weight=3)]).value is UNKNOWN
    assert Score([]).value is UNKNOWN


def test_unknown_has_no_truth_value():
    """`if score.value:` must fail loudly rather than treat Unknown as falsy-zero."""
    with pytest.raises(TypeError):
        bool(UNKNOWN)


def test_weighted_mean_uses_known_weights():
    score = Score([
        DimensionScore("safety", 1.0, weight=3),
        DimensionScore("budget", 0.0, weight=1),
        DimensionScore("eco", UNKNOWN, weight=5),
    ])
    assert score.value == pytest.approx(0.75)  # (1*3 + 0*1) / 4


def test_out_of_range_score_is_rejected_at_construction():
    with pytest.raises(ValueError):
        DimensionScore("safety", 1.4, weight=1)
