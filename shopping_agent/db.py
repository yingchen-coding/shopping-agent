"""Local SQLite store: Members, Preferences, Blocklist Entries, Watches, Snapshots.

This file holds household data — member names, birthdates, per-child safety
needs — and is gitignored. Nothing here ever ships with the project.
See docs/adr/0003.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

DB_PATH = Path(os.environ.get("SHOPPING_AGENT_DB", Path.cwd() / "preferences.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    name        TEXT PRIMARY KEY,
    birthdate   TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scope       TEXT NOT NULL CHECK (scope IN ('member', 'category')),
    scope_key   TEXT NOT NULL,          -- member name, or category name
    dimension   TEXT NOT NULL,
    weight      REAL NOT NULL,
    note        TEXT NOT NULL DEFAULT '',
    avoid       TEXT NOT NULL DEFAULT '',   -- comma-separated
    UNIQUE (scope, scope_key, dimension)
);
CREATE TABLE IF NOT EXISTS blocklist (
    value       TEXT PRIMARY KEY,       -- brand or merchant, lowercased
    kind        TEXT NOT NULL CHECK (kind IN ('brand', 'merchant')),
    reason      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    query        TEXT NOT NULL,
    beneficiary  TEXT,
    target_price REAL NOT NULL,
    notified_at  TEXT,                  -- set on the first Crossing; blocks re-alerting
    created_at   TEXT NOT NULL,
    UNIQUE (query, target_price)
);
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id    INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
    price       REAL,                   -- NULL when the check found no product at all
    product_id  TEXT,
    title       TEXT,
    merchant    TEXT,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_watch ON snapshots(watch_id, observed_at);
"""


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # WAL so a cron check-watches run and an interactive command never block
    # each other; busy_timeout covers the rarer writer-vs-writer case.
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


# ── members ──────────────────────────────────────────────────────────────────

def add_member(conn: sqlite3.Connection, name: str, birthdate: str | None = None) -> None:
    if birthdate:
        date.fromisoformat(birthdate)  # reject a malformed date at the boundary
    with conn:
        conn.execute(
            "INSERT INTO members (name, birthdate, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET birthdate=excluded.birthdate",
            (name.lower(), birthdate, _now()),
        )


def get_member(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM members WHERE name = ?", (name.lower(),)).fetchone()
    return dict(row) if row else None


def list_members(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM members ORDER BY name")]


def member_age_years(member: dict[str, Any], on: date | None = None) -> float | None:
    if not member.get("birthdate"):
        return None
    born = date.fromisoformat(member["birthdate"])
    today = on or date.today()
    return (today - born).days / 365.25


# ── preferences ──────────────────────────────────────────────────────────────

def set_preference(
    conn: sqlite3.Connection,
    scope: str,
    scope_key: str,
    dimension: str,
    weight: float,
    note: str = "",
    avoid: list[str] | None = None,
) -> None:
    with conn:
        conn.execute(
            "INSERT INTO preferences (scope, scope_key, dimension, weight, note, avoid) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(scope, scope_key, dimension) DO UPDATE SET "
            "weight=excluded.weight, note=excluded.note, avoid=excluded.avoid",
            (scope, scope_key.lower(), dimension, weight, note,
             ",".join(sorted({a.strip().lower() for a in (avoid or []) if a.strip()}))),
        )


def get_preferences(conn: sqlite3.Connection, scope: str, scope_key: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM preferences WHERE scope = ? AND scope_key = ?", (scope, scope_key.lower())
    )
    return [dict(r) for r in rows]


def all_preferences(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM preferences ORDER BY scope, scope_key, dimension")]


# ── blocklist ────────────────────────────────────────────────────────────────

def add_blocklist(conn: sqlite3.Connection, value: str, kind: str, reason: str = "") -> None:
    with conn:
        conn.execute(
            "INSERT INTO blocklist (value, kind, reason, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(value) DO UPDATE SET kind=excluded.kind, reason=excluded.reason",
            (value.strip().lower(), kind, reason, _now()),
        )


def get_blocklist(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM blocklist ORDER BY value")]


# ── watches & snapshots ──────────────────────────────────────────────────────

def add_watch(
    conn: sqlite3.Connection, query: str, target_price: float, beneficiary: str | None = None
) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO watches (query, beneficiary, target_price, created_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(query, target_price) DO NOTHING",
            (query, beneficiary.lower() if beneficiary else None, target_price, _now()),
        )
        if cur.lastrowid:
            return cur.lastrowid
    row = conn.execute(
        "SELECT id FROM watches WHERE query = ? AND target_price = ?", (query, target_price)
    ).fetchone()
    return row["id"]


def list_watches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM watches ORDER BY created_at")]


def remove_watch(conn: sqlite3.Connection, watch_id: int) -> bool:
    with conn:
        return conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,)).rowcount > 0


def record_snapshot(
    conn: sqlite3.Connection,
    watch_id: int,
    price: float | None,
    product_id: str | None = None,
    title: str | None = None,
    merchant: str | None = None,
) -> None:
    """Append-only. Written on every check, including checks that found nothing,
    so that Price History has no silent gaps."""
    with conn:
        conn.execute(
            "INSERT INTO snapshots (watch_id, price, product_id, title, merchant, observed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (watch_id, price, product_id, title, merchant, _now()),
        )


def price_history(conn: sqlite3.Connection, watch_id: int) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM snapshots WHERE watch_id = ? ORDER BY observed_at", (watch_id,))]


def mark_notified(conn: sqlite3.Connection, watch_id: int) -> None:
    with conn:
        conn.execute("UPDATE watches SET notified_at = ? WHERE id = ?", (_now(), watch_id))
