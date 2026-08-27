"""Checking Watches: Snapshots, Crossings, and the one Notification.

A Snapshot is written on every check whether or not anything changed, so Price
History has no gaps. A Notification fires only on the first Crossing — a price
that stays below target is not a new Crossing and is not announced again.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from . import db
from .search import Product, QuotaExhausted, SearchClient


@dataclass
class CheckResult:
    watch: dict[str, Any]
    price: float | None
    product: Product | None
    crossed: bool          # this check is the first Crossing
    notified: bool
    already_below: bool    # below target, but announced on an earlier check
    error: str = ""


def notify(title: str, message: str) -> None:
    """Native macOS notification. A failure here must not lose the Snapshot."""
    script = (
        f"display notification {json.dumps(message)} with title {json.dumps(title)} "
        'sound name "Glass"'
    )
    subprocess.run(["osascript", "-e", script], capture_output=True, check=False)


def _cheapest(products: list[Product]) -> Product | None:
    """Lowest Representative Price among the results.

    This is the cheapest *representative* price on the result page, not the
    cheapest merchant offer for any one product — establishing that would mean
    a billed retrieval per product. See the Representative Price entry.
    """
    priced = [p for p in products if p.representative_price is not None]
    return min(priced, key=lambda p: p.representative_price) if priced else None


def check_watch(
    conn, watch: dict[str, Any], client: SearchClient, *, respect_reserve: bool = True
) -> CheckResult:
    try:
        products = client.search(
            watch["query"], respect_reserve=respect_reserve, use_cache=False
        )
    except QuotaExhausted as exc:
        # No Snapshot: nothing was observed. Recording one would invent a gap-filler.
        return CheckResult(watch, None, None, False, False, False, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — surface the real reason, keep other watches running
        return CheckResult(watch, None, None, False, False, False, error=str(exc))

    product = _cheapest(products)
    price = product.representative_price if product else None

    db.record_snapshot(
        conn,
        watch["id"],
        price,
        product_id=product.product_id if product else None,
        title=product.title if product else None,
        merchant=product.merchant if product else None,
    )

    if price is None:
        return CheckResult(watch, None, None, False, False, False)

    below = price <= watch["target_price"]
    already_notified = bool(watch.get("notified_at"))

    if below and not already_notified:
        db.mark_notified(conn, watch["id"])
        notify(
            f"💰 ${price:.2f} — {watch['query'][:40]}",
            f"Target ${watch['target_price']:.2f} reached at "
            f"{product.merchant or 'unknown merchant'}: {product.title[:80]}",
        )
        return CheckResult(watch, price, product, True, True, False)

    return CheckResult(watch, price, product, False, False, below and already_notified)


def check_all(conn, client: SearchClient, *, respect_reserve: bool = True) -> list[CheckResult]:
    return [
        check_watch(conn, w, client, respect_reserve=respect_reserve)
        for w in db.list_watches(conn)
    ]
