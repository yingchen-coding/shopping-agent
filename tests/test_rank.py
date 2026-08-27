import pytest

from shopping_agent.preferences import Preference, merge
from shopping_agent.rank import build_candidate, rank
from shopping_agent.recalls import POSSIBLE, RecallMatch, RecallRecord
from shopping_agent.scoring import UNKNOWN
from shopping_agent.search import Product

REC = RecallRecord("1", "Some Recall", "2026-01-01", "http://cpsc/x", ["choking"], ["Widget"])


def _product(title="Widget", price=50.0, snippet=""):
    return Product("p1", title, price, "ShopCo", "http://x", 4.0, 5, snippet, False)


def test_a_preference_never_removes_a_product_it_only_scores_it():
    """Avoided terms drag the score to zero but the product stays rankable."""
    prefs = merge([Preference("material-avoid", 3, avoid=frozenset({"pvc"}))], [])
    c = build_candidate(_product(snippet="made of PVC"), prefs)
    assert c.score.value == 0.0
    assert c.product.title == "Widget"  # present, not excluded


def test_a_possible_recall_warns_and_scores_low_but_is_still_a_candidate():
    prefs = merge([Preference("safety", 3)], [])
    hit = RecallMatch(REC, POSSIBLE, "brand matches")
    c = build_candidate(_product(), prefs, recall=hit)
    assert c.score.value == pytest.approx(0.2)
    assert any("possible recall" in w for w in c.warnings)
    assert REC.url in c.warnings[0]


def test_absence_of_a_recall_is_not_scored_as_proof_of_safety():
    prefs = merge([Preference("safety", 1)], [])
    assert build_candidate(_product(), prefs, recall=None).score.value == pytest.approx(0.8)


def test_eco_is_unknown_rather_than_guessed_from_the_listing():
    prefs = merge([Preference("eco", 3)], [])
    c = build_candidate(_product(snippet="eco-friendly green natural"), prefs)
    assert c.score.dimensions[0].value is UNKNOWN
    assert c.score.value is UNKNOWN


def test_budget_is_unknown_when_no_budget_was_given():
    prefs = merge([Preference("budget", 1)], [])
    assert build_candidate(_product(price=50.0), prefs, budget=None).score.value is UNKNOWN


def test_budget_scores_full_marks_within_target_and_degrades_above_it():
    prefs = merge([Preference("budget", 1)], [])
    assert build_candidate(_product(price=20.0), prefs, budget=25.0).score.value == 1.0
    over = build_candidate(_product(price=50.0), prefs, budget=25.0).score.value
    assert 0.0 <= over < 1.0


def test_unknown_scores_sort_last_rather_than_as_zero():
    prefs_known = merge([Preference("budget", 1)], [])
    prefs_unknown = merge([Preference("eco", 1)], [])
    bad = build_candidate(_product(title="Bad", price=100.0), prefs_known, budget=10.0)
    unknown = build_candidate(_product(title="Unknown"), prefs_unknown)
    good = build_candidate(_product(title="Good", price=5.0), prefs_known, budget=10.0)

    order = [c.product.title for c in rank([unknown, bad, good])]
    assert order[0] == "Good"
    assert order[-1] == "Unknown", "unassessed must not outrank assessed-bad"


def test_under_three_beneficiary_gets_a_small_parts_warning():
    prefs = merge([Preference("safety", 1)], [])
    member = {"name": "alex", "birthdate": "2024-01-01"}
    c = build_candidate(_product(snippet="contains small parts"), prefs, member=member)
    assert any("small parts" in w for w in c.warnings)
