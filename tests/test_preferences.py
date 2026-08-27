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
    effective = merge([], [])
    assert effective.weight("safety") == 0
    assert effective.avoided("safety") == frozenset()
