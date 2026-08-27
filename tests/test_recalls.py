from shopping_agent.recalls import CONFIRMED, POSSIBLE, RecallRecord, match

CHOKING = RecallRecord(
    recall_id="1",
    title="TooyBing Wooden Bead Stacking Toys Recalled Due to Choking Hazard",
    date="2026-02-01",
    url="https://www.cpsc.gov/Recalls/example",
    hazards=["wooden beads pose a choking hazard to young children"],
    product_names=["TooyBing Wooden Bead Stacking Toy"],
)


def test_brand_plus_product_type_confirms_and_vetoes():
    hit = match("TooyBing Wooden Bead Stacker", "tooybing", [CHOKING])
    assert hit.tier == CONFIRMED
    assert hit.vetoes is True


def test_brand_alone_is_only_possible_and_never_vetoes():
    """The core of docs/adr/0001: weak evidence warns, it does not remove."""
    hit = match("TooyBing Rain Jacket", "tooybing", [CHOKING])
    assert hit.tier == POSSIBLE
    assert hit.vetoes is False


def test_title_similarity_without_the_brand_is_only_possible():
    hit = match("Melissa & Doug Wooden Bead Stacking Toy", "melissa", [CHOKING])
    assert hit.tier == POSSIBLE
    assert hit.vetoes is False


def test_unrelated_product_does_not_match_at_all():
    assert match("Graco TurboBooster Car Seat", "graco", [CHOKING]) is None


def test_generic_child_words_alone_do_not_create_a_match():
    """'toddler', 'kids' etc. are noise — matching on them would flag everything."""
    assert match("Kids Toddler Baby Set", "acme", [CHOKING]) is None


def test_no_records_means_no_match():
    assert match("anything", "acme", []) is None


def test_a_truthful_user_agent_is_sent(monkeypatch):
    """CPSC 403s the HTTP library's default UA, so the identifying header is
    load-bearing: without it the safety veto silently stops working."""
    import shopping_agent.recalls as r

    seen = {}

    class Resp:
        status_code = 200
        def json(self):
            return []

    def fake_get(url, params=None, headers=None, timeout=None):
        seen["headers"] = headers or {}
        return Resp()

    monkeypatch.setattr(r.requests, "get", fake_get)
    r.fetch_recalls("toy")

    ua = seen["headers"].get("User-Agent", "")
    assert "shopping-agent" in ua
    assert "python-requests" not in ua
