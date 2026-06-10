"""CLI entrypoint. Step 2 implements --backfill; --incremental / --full-resync are Step 3."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="deedleague-pipeline")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--backfill", action="store_true", help="seed both approved seasons")
    mode.add_argument("--incremental", action="store_true", help="(Step 3)")
    mode.add_argument("--full-resync", action="store_true", help="(Step 3)")
    parser.add_argument("--season", dest="seasons", action="append")
    parser.add_argument("--game")
    args = parser.parse_args()

    if args.backfill:
        _run_backfill()
        return
    if args.incremental:
        print("TODO: incremental not implemented (Step 3)")
        return
    if args.full_resync:
        print("TODO: full-resync not implemented (Step 3)")
        return
    print("No mode selected. Use --backfill (Step 2).")


def _run_backfill() -> None:
    from . import db
    from .report import (
        coverage_counts,
        standings_sanity_from_db,
        validate_golden_from_db,
    )
    from .scraper import run_backfill

    summary = run_backfill(progress=True)
    counts = coverage_counts(summary.results)

    print("\n===== BACKFILL SUMMARY =====")
    for s in summary.seasons:
        n = sum(1 for r in summary.results if r.season_id == s.id)
        print(f"  {s.name}: {n} men's games  (division {s.mens_division_id})")
    print(
        f"  totals: {counts['total']} games | full={counts['full']} "
        f"partial={counts['partial']} missing={counts['missing']} "
        f"| loaded={counts['loaded']} failed={counts['failed']}"
    )
    print(
        f"  quality: points_mismatches={counts['points_mismatches']} "
        f"parse_failures={counts['parse_failures']} orphan_athletes={counts['orphan_athletes']}"
    )

    conn = db.connect()
    try:
        golden = validate_golden_from_db(conn)
        print("\n===== GOLDEN RECORD (J.Moss, from DB) =====")
        print(f"  expected: {golden['expected']}")
        print(f"  got:      {golden['got']}")
        print(f"  RESULT:   {'PASS' if golden['pass'] else 'FAIL'}")

        for s in summary.seasons:
            if s.name.startswith("2025-2026"):
                st = standings_sanity_from_db(conn, s.id)
                print(f"\n===== STANDINGS SANITY {s.name} (from game_competitors) =====")
                for name, w, ls in st["top"]:
                    print(f"  TOP    {name}: {w}-{ls}")
                for name, w, ls in st["bottom"]:
                    print(f"  BOTTOM {name}: {w}-{ls}")
    finally:
        conn.close()

    failed = [r for r in summary.results if r.status == "failed"]
    if failed:
        print("\n===== FAILED GAMES =====", file=sys.stderr)
        for r in failed[:50]:
            print(f"  {r.game_id}: {r.note}", file=sys.stderr)
