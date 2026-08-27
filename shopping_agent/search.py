"""Product search, and the quota discipline that keeps it on the free tier.

Every billed call is preceded by a balance check, which is itself free. The
balance is read from the API rather than counted locally, because a local
counter drifts and the authoritative number costs nothing. See docs/adr/0006.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

SEARCH_URL = "https://serpapi.com/search"
ACCOUNT_URL = "https://serpapi.com/account"

# Scheduled work may not spend below this; it is held for interactive use, so a
# cron job can never leave you unable to run a search yourself.
DEFAULT_RESERVE = 100
MAX_WATCHES = 5

CACHE_DIR = Path(os.environ.get("SHOPPING_AGENT_CACHE", Path.cwd() / ".cache"))
CACHE_TTL_SECONDS = 24 * 60 * 60


class SearchError(RuntimeError):
    """Raised rather than returning empty, so a failure is never read as 'nothing found'."""


class QuotaExhausted(SearchError):
    """The call was refused before being made, to stay inside the free tier."""


@dataclass(frozen=True)
class Product:
    """One distinct item. Identity comes from the search source — see docs/adr/0005."""

    product_id: str
    title: str
    representative_price: float | None
    merchant: str | None
    link: str | None
    rating: float | None
    reviews: int | None
    snippet: str
    multiple_merchants: bool

    @property
    def brand_guess(self) -> str:
        """First token of the title, lowercased.

        A guess, not a field: the search source exposes no brand. Used only to
        gate recall matching, where a wrong guess costs a warning, never a veto.
        """
        return self.title.strip().split()[0].lower() if self.title.strip() else ""


def _cache_path(key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:120]
    return CACHE_DIR / f"{safe}.json"


def _read_cache(key: str) -> dict[str, Any] | None:
    path = _cache_path(key)
    if not path.exists() or time.time() - path.stat().st_mtime > CACHE_TTL_SECONDS:
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(key: str, payload: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _cache_path(key).write_text(json.dumps(payload))
    except OSError:
        pass  # a cache we cannot write is a slower run, not a failed one


class SearchClient:
    def __init__(self, api_key: str | None = None, reserve: int = DEFAULT_RESERVE) -> None:
        self.api_key = api_key or os.environ.get("SERPAPI_KEY")
        if not self.api_key:
            raise SearchError(
                "SERPAPI_KEY is not set. Export it (or add it to ~/.env) before searching."
            )
        self.reserve = reserve

    def quota(self) -> dict[str, Any]:
        """Remaining balance. This call is not itself billed."""
        resp = requests.get(ACCOUNT_URL, params={"api_key": self.api_key}, timeout=20)
        if resp.status_code != 200:
            raise SearchError(f"quota check failed: HTTP {resp.status_code} {resp.text[:200]}")
        data = resp.json()
        return {
            "plan": data.get("plan_name"),
            "used_this_month": data.get("this_month_usage"),
            "left": data.get("total_searches_left"),
            "per_month": data.get("searches_per_month"),
        }

    def _require_budget(self, *, respect_reserve: bool) -> None:
        left = self.quota()["left"]
        if left is None:
            return
        floor = self.reserve if respect_reserve else 0
        if left <= floor:
            raise QuotaExhausted(
                f"{left} searches left this month; scheduled work stops at a reserve of {floor} "
                "so interactive searches stay possible. Use --no-reserve to spend it anyway."
            )

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        respect_reserve: bool = False,
        use_cache: bool = True,
    ) -> list[Product]:
        cache_key = f"shop_{query}"
        payload = _read_cache(cache_key) if use_cache else None

        if payload is None:
            self._require_budget(respect_reserve=respect_reserve)
            resp = requests.get(
                SEARCH_URL,
                params={
                    "engine": "google_shopping",
                    "q": query,
                    "gl": "us",
                    "hl": "en",
                    "api_key": self.api_key,
                },
                timeout=45,
            )
            if resp.status_code != 200:
                raise SearchError(f"search failed: HTTP {resp.status_code} {resp.text[:200]}")
            payload = resp.json()
            if payload.get("error"):
                raise SearchError(f"search failed: {payload['error']}")
            _write_cache(cache_key, payload)

        return [_to_product(r) for r in (payload.get("shopping_results") or [])[:limit]]


def _to_product(row: dict[str, Any]) -> Product:
    price = row.get("extracted_price")
    return Product(
        product_id=str(row.get("product_id") or row.get("position") or ""),
        title=row.get("title") or "",
        representative_price=float(price) if isinstance(price, (int, float)) else None,
        merchant=row.get("source"),
        link=row.get("product_link"),
        rating=row.get("rating"),
        reviews=row.get("reviews"),
        snippet=row.get("snippet") or "",
        multiple_merchants=bool(row.get("multiple_sources")),
    )
