"""Command-line interface."""
from __future__ import annotations

import argparse
import sys

from . import db
from .preferences import Preference, merge
from .rank import Vetoed, build_candidate, rank
from .recalls import RecallError, fetch_recalls, match
from .scoring import DIMENSIONS, UNKNOWN
from .search import MAX_WATCHES, SearchClient, SearchError


def _fmt_score(value) -> str:
    return "  n/a" if value is UNKNOWN else f"{float(value):5.2f}"


def _blocked(product, blocklist) -> str:
    text = f"{product.title} {product.merchant or ''}".lower()
    for entry in blocklist:
        if entry["value"] in text:
            return f"{entry['kind']} '{entry['value']}' is blocklisted"
    return ""


def cmd_add_member(args, conn) -> int:
    db.add_member(conn, args.name, args.birthdate)
    print(f"member '{args.name.lower()}' saved")
    return 0


def cmd_members(args, conn) -> int:
    members = db.list_members(conn)
    if not members:
        print("no members yet — add one with: shopping-agent add-member <name> --birthdate YYYY-MM-DD")
        return 0
    for m in members:
        age = db.member_age_years(m)
        print(f"  {m['name']:12} {m['birthdate'] or '(no birthdate)':12} "
              f"{f'{age:.1f}y' if age is not None else ''}")
    return 0


def cmd_prefer(args, conn) -> int:
    if bool(args.member) == bool(args.category):
        print("error: give exactly one of --member or --category", file=sys.stderr)
        return 1
    scope = "member" if args.member else "category"
    key = args.member or args.category
    if scope == "member" and not db.get_member(conn, key):
        print(f"error: no member '{key}'. Add them first.", file=sys.stderr)
        return 1
    db.set_preference(conn, scope, key, args.dimension, args.weight, args.note or "", args.avoid)
    print(f"{scope} preference saved: {key} / {args.dimension} weight={args.weight}")
    return 0


def cmd_preferences(args, conn) -> int:
    rows = db.all_preferences(conn)
    if not rows:
        print("no preferences yet")
        return 0
    for r in rows:
        avoid = f"  avoid: {r['avoid']}" if r["avoid"] else ""
        note = f"  “{r['note']}”" if r["note"] else ""
        print(f"  {r['scope']:8} {r['scope_key']:12} {r['dimension']:14} w={r['weight']}{avoid}{note}")
    return 0


def cmd_block(args, conn) -> int:
    db.add_blocklist(conn, args.value, args.kind, args.reason or "")
    print(f"blocklisted {args.kind}: {args.value.lower()}")
    return 0


def cmd_search(args, conn) -> int:
    member = db.get_member(conn, args.member) if args.member else None
    if args.member and not member:
        print(f"error: no member '{args.member}'", file=sys.stderr)
        return 1

    member_prefs = [
        Preference(r["dimension"], r["weight"], r["note"],
                   frozenset(a for a in r["avoid"].split(",") if a))
        for r in (db.get_preferences(conn, "member", args.member) if args.member else [])
    ]
    category_prefs = [
        Preference(r["dimension"], r["weight"], r["note"],
                   frozenset(a for a in r["avoid"].split(",") if a))
        for r in (db.get_preferences(conn, "category", args.category) if args.category else [])
    ]
    prefs = merge(member_prefs, category_prefs)

    client = SearchClient()
    products = client.search(args.query, limit=args.limit, respect_reserve=False)
    if not products:
        print(f"no products found for {args.query!r}")
        return 0

    try:
        records = fetch_recalls(args.query)
        recall_note = f"{len(records)} CPSC recall record(s) checked"
    except RecallError as exc:
        # The safety check failing must never look like a clean bill of health.
        records = []
        recall_note = f"⚠️  CPSC check FAILED ({exc}) — safety not verified"

    blocklist = db.get_blocklist(conn)
    candidates, vetoed = [], []

    for product in products:
        reason = _blocked(product, blocklist)
        if reason:
            vetoed.append(Vetoed(product, reason))
            continue
        hit = match(product.title, product.brand_guess, records) if records else None
        if hit and hit.vetoes:
            vetoed.append(Vetoed(product, f"confirmed recall — {hit.why}", hit.record.url))
            continue
        candidates.append(
            build_candidate(product, prefs, recall=hit, budget=args.budget, member=member)
        )

    print(f"\n{len(products)} product(s) for {args.query!r} · {recall_note}")
    if args.member:
        print(f"ranked for {args.member} · preferences: "
              f"{', '.join(prefs.dimensions) or 'none set'}")
    if not prefs.dimensions:
        print("note: no preferences apply, so ranking is by search order only")

    for c in rank(candidates)[:args.limit]:
        price = (f"${c.product.representative_price:.2f}"
                 if c.product.representative_price is not None else "no price")
        print(f"\n  {_fmt_score(c.score.value)}  {c.product.title[:66]}")
        print(f"         {price} at {c.product.merchant or '?'}"
              f"{'  (other merchants sell this)' if c.product.multiple_merchants else ''}"
              f"   evidence {c.score.evidence_ratio}")
        for d in c.score.dimensions:
            mark = "?" if not d.is_known else f"{float(d.value):.2f}"
            print(f"           {d.dimension:14} {mark:>5} ×{d.weight:<4g} {d.reason}")
        for w in c.warnings:
            print(f"           ⚠️  {w}")
        if c.product.link:
            print(f"           {c.product.link[:100]}")

    if vetoed:
        print(f"\n  excluded ({len(vetoed)}):")
        for v in vetoed:
            print(f"    ✗ {v.product.title[:60]} — {v.reason}")
            if v.evidence_url:
                print(f"      {v.evidence_url}")
    return 0


def cmd_watch(args, conn) -> int:
    existing = db.list_watches(conn)
    if len(existing) >= MAX_WATCHES and not args.force:
        print(f"error: {len(existing)} watches already exist. Each costs one search per day, and "
              f"the free tier is 250/month.\nUse --force to add anyway.", file=sys.stderr)
        return 1
    watch_id = db.add_watch(conn, args.query, args.target, args.member)
    print(f"watch #{watch_id}: {args.query!r} target ${args.target:.2f}")
    return 0


def cmd_watches(args, conn) -> int:
    watches = db.list_watches(conn)
    if not watches:
        print("no watches")
        return 0
    for w in watches:
        history = db.price_history(conn, w["id"])
        prices = [h["price"] for h in history if h["price"] is not None]
        last = f"last ${prices[-1]:.2f}" if prices else "no price yet"
        state = "notified" if w["notified_at"] else "watching"
        print(f"  #{w['id']}  ${w['target_price']:<8.2f} {state:9} {last:16} "
              f"{len(history)} snapshot(s)  {w['query'][:40]}")
    return 0


def cmd_unwatch(args, conn) -> int:
    print(f"watch #{args.id} removed" if db.remove_watch(conn, args.id)
          else f"no watch #{args.id}")
    return 0


def cmd_check_watches(args, conn) -> int:
    from .watch import check_all
    results = check_all(conn, SearchClient(), respect_reserve=not args.no_reserve)
    if not results:
        print("no watches to check")
        return 0
    for r in results:
        if r.error:
            print(f"  #{r.watch['id']} {r.watch['query'][:38]:40} ERROR: {r.error}")
        elif r.price is None:
            print(f"  #{r.watch['id']} {r.watch['query'][:38]:40} no priced product found")
        else:
            state = ("🟢 CROSSED — notified" if r.crossed
                     else "below target (already notified)" if r.already_below
                     else f"above target ${r.watch['target_price']:.2f}")
            print(f"  #{r.watch['id']} {r.watch['query'][:38]:40} ${r.price:<9.2f} {state}")
    return 0


def cmd_history(args, conn) -> int:
    rows = db.price_history(conn, args.id)
    if not rows:
        print(f"no snapshots for watch #{args.id}")
        return 0
    print(f"forward-only history for watch #{args.id} — begins when the watch was created")
    for r in rows:
        price = f"${r['price']:.2f}" if r["price"] is not None else "(none found)"
        print(f"  {r['observed_at'][:19]}  {price:>12}  {(r['merchant'] or ''):16} "
              f"{(r['title'] or '')[:44]}")
    return 0


def cmd_quota(args, conn) -> int:
    q = SearchClient().quota()
    print(f"  plan          {q['plan']}")
    print(f"  used          {q['used_this_month']} / {q['per_month']}")
    print(f"  left          {q['left']}")
    watches = len(db.list_watches(conn))
    print(f"  watches       {watches} (≈{watches * 30} searches/month at one check per day)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shopping-agent", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add-member", help="Add or update a household member")
    p.add_argument("name"); p.add_argument("--birthdate", help="YYYY-MM-DD")
    p.set_defaults(func=cmd_add_member)

    sub.add_parser("members", help="List members").set_defaults(func=cmd_members)

    p = sub.add_parser("prefer", help="Store a member-level or category-level preference")
    p.add_argument("--member"); p.add_argument("--category")
    p.add_argument("--dimension", required=True, choices=DIMENSIONS)
    p.add_argument("--weight", type=float, default=1.0)
    p.add_argument("--note", help="the household's own wording")
    p.add_argument("--avoid", nargs="*", default=[], help="terms to avoid on this dimension")
    p.set_defaults(func=cmd_prefer)

    sub.add_parser("preferences", help="List stored preferences").set_defaults(func=cmd_preferences)

    p = sub.add_parser("block", help="Blocklist a brand or merchant (this can veto)")
    p.add_argument("value"); p.add_argument("--kind", choices=["brand", "merchant"], default="brand")
    p.add_argument("--reason")
    p.set_defaults(func=cmd_block)

    p = sub.add_parser("search", help="Search, veto, and rank products for a need")
    p.add_argument("query")
    p.add_argument("--for", dest="member", help="beneficiary — whose preferences apply")
    p.add_argument("--category", help="category whose family-wide preferences apply")
    p.add_argument("--budget", type=float, help="target price, used by the budget dimension")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("watch", help="Watch a query's price against a target")
    p.add_argument("query"); p.add_argument("--target", type=float, required=True)
    p.add_argument("--for", dest="member"); p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_watch)

    sub.add_parser("watches", help="List watches").set_defaults(func=cmd_watches)

    p = sub.add_parser("unwatch", help="Remove a watch"); p.add_argument("id", type=int)
    p.set_defaults(func=cmd_unwatch)

    p = sub.add_parser("check-watches", help="Check every watch once (for cron)")
    p.add_argument("--no-reserve", action="store_true",
                   help="spend into the interactive reserve as well")
    p.set_defaults(func=cmd_check_watches)

    p = sub.add_parser("history", help="Show a watch's forward-only price history")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_history)

    sub.add_parser("quota", help="Show remaining search quota").set_defaults(func=cmd_quota)

    args = parser.parse_args(argv)
    conn = db.connect()
    try:
        return args.func(args, conn)
    except (SearchError, RecallError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
