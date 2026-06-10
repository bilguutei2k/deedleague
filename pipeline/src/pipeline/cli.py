"""CLI entrypoint. Modes (§7): --backfill, --incremental, --full-resync,
plus targeted --season / --game filters."""

from __future__ import annotations

import argparse
import sys
from collections import Counter


def main() -> None:
    parser = argparse.ArgumentParser(prog="deedleague-pipeline")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--backfill", action="store_true", help="seed both approved seasons")
    mode.add_argument("--incremental", action="store_true", help="fetch only selected games")
    mode.add_argument("--full-resync", action="store_true", help="re-fetch every game")
    parser.add_argument("--season", dest="seasons", action="append", help="restrict to season id(s)")
    parser.add_argument("--game", dest="games", action="append", help="restrict to game id(s)")
    args = parser.parse_args()

    if args.backfill:
        selected = "backfill"
    elif args.full_resync:
        selected = "full_resync"
    elif args.incremental:
        selected = "incremental"
    elif args.games or args.seasons:
        selected = "incremental"  # targeted run
    else:
        print("No mode selected. Use --backfill | --incremental | --full-resync.")
        return

    _run(
        selected,
        season_ids=set(args.seasons) if args.seasons else None,
        game_ids=set(args.games) if args.games else None,
    )


def _run(mode: str, season_ids: set[str] | None, game_ids: set[str] | None) -> None:
    from . import db
    from .report import standings_sanity_from_db, validate_golden_from_db
    from .scraper import run_ingest

    summary = run_ingest(mode, season_ids=season_ids, game_ids=game_ids, progress=True)
    status = Counter(r.status for r in summary.results)
    cov = Counter(r.coverage for r in summary.results)

    print(f"\n===== {mode.upper()} SUMMARY =====")
    for s in summary.seasons:
        n = sum(1 for r in summary.results if r.season_id == s.id)
        print(f"  {s.name}: {n} games processed")
    print(
        f"  totals: {len(summary.results)} processed | "
        f"loaded(changed)={status.get('loaded', 0)} unchanged={status.get('unchanged', 0)} "
        f"failed={status.get('failed', 0)}"
    )
    print(
        f"  coverage: full={cov.get('full', 0)} partial={cov.get('partial', 0)} "
        f"missing={cov.get('missing', 0)}"
    )
    if summary.errors:
        print(f"  errors: {len(summary.errors)} (see scrape_runs / stderr)")

    # Golden + standings re-verification on full passes.
    if mode in ("backfill", "full_resync"):
        conn = db.connect()
        try:
            golden = validate_golden_from_db(conn)
            print("\n===== GOLDEN RECORD (J.Moss, from DB) =====")
            print(f"  got: {golden['got']}  -> {'PASS' if golden['pass'] else 'FAIL'}")
            for s in summary.seasons:
                if s.name.startswith("2025-2026"):
                    st = standings_sanity_from_db(conn, s.id)
                    top = st["top"][0] if st["top"] else None
                    bot = st["bottom"][-1] if st["bottom"] else None
                    print(f"  standings 2025-26: top={top} bottom={bot}")
        finally:
            conn.close()

    failed = [r for r in summary.results if r.status == "failed"]
    if failed:
        print("\n===== FAILED GAMES =====", file=sys.stderr)
        for r in failed[:50]:
            print(f"  {r.game_id}: {r.note}", file=sys.stderr)
