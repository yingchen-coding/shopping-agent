from shopping_agent import db
from shopping_agent.search import Product
from shopping_agent.watch import check_watch


def _conn(tmp_path):
    return db.connect(tmp_path / "t.db")


class FakeClient:
    """Stands in for the search source; returns a fixed price per call."""

    def __init__(self, prices):
        self.prices = list(prices)
        self.calls = 0

    def search(self, query, **kwargs):
        self.calls += 1
        price = self.prices[min(self.calls - 1, len(self.prices) - 1)]
        if price is None:
            return []
        return [Product("p1", "Widget", price, "ShopCo", "http://x", 4.5, 10, "", True)]


def test_notification_fires_once_on_the_first_crossing_only(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr("shopping_agent.watch.notify", lambda t, m: sent.append(t))
    conn = _conn(tmp_path)
    db.add_watch(conn, "widget", target_price=100.0)
    client = FakeClient([120.0, 90.0, 85.0])

    first = check_watch(conn, db.list_watches(conn)[0], client)
    assert first.crossed is False and sent == []

    second = check_watch(conn, db.list_watches(conn)[0], client)
    assert second.crossed is True and len(sent) == 1

    third = check_watch(conn, db.list_watches(conn)[0], client)
    assert third.crossed is False
    assert third.already_below is True
    assert len(sent) == 1, "a price staying below target must not re-alert"


def test_a_snapshot_is_written_on_every_check_including_empty_ones(tmp_path, monkeypatch):
    monkeypatch.setattr("shopping_agent.watch.notify", lambda t, m: None)
    conn = _conn(tmp_path)
    wid = db.add_watch(conn, "widget", target_price=10.0)
    client = FakeClient([50.0, None, 40.0])

    for _ in range(3):
        check_watch(conn, db.list_watches(conn)[0], client)

    history = db.price_history(conn, wid)
    assert len(history) == 3, "history must have no gaps"
    assert [h["price"] for h in history] == [50.0, None, 40.0]


def test_quota_refusal_records_no_snapshot(tmp_path):
    """Nothing was observed, so inventing a data point would falsify the history."""
    from shopping_agent.search import QuotaExhausted

    class Refusing:
        def search(self, *a, **k):
            raise QuotaExhausted("reserve reached")

    conn = _conn(tmp_path)
    wid = db.add_watch(conn, "widget", target_price=10.0)
    result = check_watch(conn, db.list_watches(conn)[0], Refusing())

    assert "reserve" in result.error
    assert db.price_history(conn, wid) == []
