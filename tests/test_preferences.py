from shopping_agent.preferences import Preference, merge


def test_stricter_weight_wins_regardless_of_level_order():
    member = [Preference("safety", weight=1)]
    category = [Preference("safety", weight=3)]
    assert merge(member, category).weight("safety") == 3
    assert merge(category, member).weight("safety") == 3


def test_avoid_lists_are_unioned_not_replaced():
    """A brand avoided family-wide stays avoided when buying for one child."""
    member = [Preference("material-avoid", 2, avoid=frozenset({"pvc"}))]
    category = [Preference("material-avoid", 1, avoid=frozenset({"bpa"}))]
    assert merge(member, category).avoided("material-avoid") == {"pvc", "bpa"}


def test_both_levels_contribute_their_own_dimensions():
    effective = merge([Preference("safety", 3)], [Preference("eco", 2)])
    assert effective.weight("safety") == 3
    assert effective.weight("eco") == 2


def test_notes_from_both_levels_are_kept():
    effective = merge([Preference("safety", 1, note="安全第一")],
                      [Preference("safety", 2, note="no small parts")])
    assert "安全第一" in effective.by_dimension["safety"].note
    assert "no small parts" in effective.by_dimension["safety"].note


def test_unset_dimension_has_zero_weight_and_no_avoids():
    """Checked against a non-empty set: an empty one now falls back to the
    baseline, which is a different case covered separately below."""
    effective = merge([Preference("safety", 2)], [])
    assert effective.weight("eco") == 0
    assert effective.avoided("eco") == frozenset()


def test_an_empty_set_falls_back_to_the_baseline_rather_than_scoring_nothing():
    """With nothing stored, every product would otherwise be unscorable — which
    reads as a broken search rather than as an unconfigured one."""
    effective = merge([], [])
    assert effective.is_baseline is True
    assert effective.dimensions == ["safety", "reliability", "budget"]
    assert all(effective.weight(d) > 0 for d in effective.dimensions)


def test_the_baseline_is_not_applied_once_anything_is_stored():
    """A household that stated only eco has deliberately not asked about budget."""
    effective = merge([Preference("eco", 2)], [])
    assert effective.is_baseline is False
    assert effective.dimensions == ["eco"]
    assert effective.weight("budget") == 0


def test_a_category_only_match_still_suppresses_the_baseline():
    effective = merge([], [Preference("material-avoid", 1)])
    assert effective.is_baseline is False
    assert effective.dimensions == ["material-avoid"]
