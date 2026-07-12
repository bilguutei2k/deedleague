from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import psycopg

from pipeline import cli, scraper
from pipeline import db as pipeline_db
from pipeline.client import MsportsClient
from pipeline.discovery import DiscoveredGame
from pipeline.loader import load_game
from pipeline.normalizer import normalize_game
from pipeline.parser import parse_game
from pipeline.refresh import select_incremental


FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "golden_game_44a47063.json")


def game_result(**overrides) -> scraper.GameResult:
    values = {
        "game_id": "game-1",
        "season_id": "season-1",
        "is_ended": True,
        "status": "loaded",
        "coverage": "full",
        "player_stat_rows": 10,
        "parse_failures": 0,
        "orphan_athletes": 0,
        "fallback_athletes": 0,
        "unknown_stat_terms": 0,
        "points_mismatch": False,
        "note": "",
    }
    values.update(overrides)
    return scraper.GameResult(**values)


class FakeSession:
    def __init__(self) -> None:
        self.conn = Mock()
        self.reset_calls = 0
        self.closed = False

    def reset(self) -> None:
        self.reset_calls += 1

    def close(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class RunIngestTests(unittest.TestCase):
    def run_with(
        self,
        *,
        result: scraper.GameResult | None = None,
        schedule: list | None = None,
        discover_error: Exception | None = None,
        seed_error: Exception | None = None,
        standings_error: Exception | None = None,
        process_side_effect=None,
        finalize_side_effect=None,
    ):
        session = FakeSession()
        client = FakeClient()
        season = SimpleNamespace(
            id="season-1",
            name="Season 1",
            start_date="2025-01-01",
            end_date="2025-12-31",
            parent_league_id="league-1",
            mens_division_id="division-1",
            mens_division_name="Men",
        )
        selected_schedule = [SimpleNamespace(id="game-1")] if schedule is None else schedule
        finalizer = Mock(side_effect=finalize_side_effect)

        with ExitStack() as stack:
            stack.enter_context(patch.object(scraper, "MsportsClient", return_value=client))
            stack.enter_context(patch.object(scraper.db, "Session", return_value=session))
            stack.enter_context(patch.object(scraper.db, "create_scrape_run", return_value="run-1"))
            stack.enter_context(patch.object(scraper.db, "finalize_scrape_run", finalizer))
            stack.enter_context(patch.object(scraper.db, "get_existing_games", return_value={}))
            if discover_error:
                stack.enter_context(patch.object(scraper, "discover_seasons", side_effect=discover_error))
            else:
                stack.enter_context(patch.object(scraper, "discover_seasons", return_value=[season]))
            stack.enter_context(patch.object(scraper, "discover_schedule", return_value=selected_schedule))
            stack.enter_context(patch.object(scraper, "_seed_seasons", side_effect=seed_error))
            stack.enter_context(
                patch.object(
                    scraper,
                    "_process_game",
                    return_value=result or game_result(),
                    side_effect=process_side_effect,
                )
            )
            stack.enter_context(
                patch(
                    "pipeline.statcalc.recompute_standings",
                    side_effect=standings_error,
                )
            )
            summary = scraper.run_ingest("incremental", progress=False)
        return summary, finalizer, session, client

    def test_fully_successful_run(self):
        summary, finalizer, session, client = self.run_with()
        self.assertEqual(summary.status, "ok")
        self.assertEqual(finalizer.call_args.kwargs["status"], "ok")
        self.assertIsNone(finalizer.call_args.kwargs["notes"])
        self.assertTrue(session.closed)
        self.assertTrue(client.closed)

    def test_failed_game_makes_run_partial(self):
        summary, finalizer, *_ = self.run_with(
            result=game_result(status="failed", coverage="missing", note="bad payload")
        )
        self.assertEqual(summary.status, "partial")
        self.assertEqual(finalizer.call_args.kwargs["status"], "partial")
        notes = json.loads(finalizer.call_args.kwargs["notes"])
        self.assertEqual(notes["failed_count"], 1)

    def test_quality_issue_makes_run_partial(self):
        summary, finalizer, *_ = self.run_with(result=game_result(points_mismatch=True))
        self.assertEqual(summary.status, "partial")
        notes = json.loads(finalizer.call_args.kwargs["notes"])
        self.assertEqual(notes["quality_issues"][0]["issues"], ["points_mismatch"])

    def test_discovery_failure_finalizes_and_propagates(self):
        with self.assertRaisesRegex(RuntimeError, "discovery failed"):
            self.run_with(discover_error=RuntimeError("discovery failed"))

    def test_database_setup_failure_finalizes_and_propagates(self):
        with self.assertRaisesRegex(RuntimeError, "seed failed"):
            self.run_with(seed_error=RuntimeError("seed failed"))

    def test_standings_failure_finalizes_and_propagates(self):
        with self.assertRaisesRegex(RuntimeError, "standings failed"):
            self.run_with(standings_error=RuntimeError("standings failed"))

    def test_finalization_failure_is_retried_as_failed_and_propagates(self):
        with self.assertRaisesRegex(RuntimeError, "finalize failed"):
            self.run_with(finalize_side_effect=[RuntimeError("finalize failed"), None])

    def test_no_selected_games_is_successful(self):
        summary, finalizer, *_ = self.run_with(schedule=[])
        self.assertEqual(summary.status, "ok")
        self.assertEqual(finalizer.call_args.kwargs["games_checked"], 0)

    def test_retry_exhaustion_makes_run_partial(self):
        summary, finalizer, session, _ = self.run_with(
            process_side_effect=psycopg.OperationalError("connection lost")
        )
        self.assertEqual(summary.status, "partial")
        self.assertEqual(summary.results[0].status, "failed")
        self.assertEqual(session.reset_calls, 2)
        self.assertEqual(finalizer.call_args.kwargs["status"], "partial")

    def test_persisted_errors_redact_credentials(self):
        error = scraper._safe_error(
            "postgresql://user:password@db.example/test password=visible token=visible"
        )
        self.assertNotIn("password@", error)
        self.assertNotIn("=visible", error)


class RunPersistenceTests(unittest.TestCase):
    def test_terminal_run_update_always_sets_finished_at(self):
        conn = MagicMock()
        pipeline_db.finalize_scrape_run(
            conn,
            "run-1",
            status="ok",
            games_checked=0,
            games_changed=0,
            notes=None,
        )
        query = conn.cursor.return_value.__enter__.return_value.execute.call_args.args[0]
        self.assertIn("finished_at = now()", query)
        conn.commit.assert_called_once_with()


class CliTests(unittest.TestCase):
    def test_missing_mode_returns_two(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = cli.main([])
        self.assertEqual(code, 2)
        self.assertIn("no mode selected", stderr.getvalue())

    def test_successful_execution_returns_zero(self):
        with patch.object(cli, "_run", return_value=0):
            self.assertEqual(cli.main(["--incremental"]), 0)

    def test_partial_execution_returns_one(self):
        summary = SimpleNamespace(status="partial", results=[], seasons=[], errors=[])
        with patch("pipeline.scraper.run_ingest", return_value=summary):
            self.assertEqual(cli._run("incremental", None, None), 1)

    def test_golden_failure_returns_one(self):
        summary = SimpleNamespace(status="ok", results=[], seasons=[], errors=[])
        conn = Mock()
        with (
            patch("pipeline.scraper.run_ingest", return_value=summary),
            patch("pipeline.db.connect", return_value=conn),
            patch("pipeline.report.validate_golden_from_db", return_value={"got": {}, "pass": False}),
        ):
            self.assertEqual(cli._run("full_resync", None, None), 1)


class NormalizerQualityTests(unittest.TestCase):
    def test_unknown_stat_term_is_reported(self):
        with open(FIXTURE, encoding="utf-8") as handle:
            raw = json.load(handle)
        raw["data"]["game"]["stats"]["nodes"].append(
            {
                "gameTime": 1,
                "teamId": None,
                "athleteId": raw["data"]["game"]["memberships"]["nodes"][0]["athlete"]["id"],
                "periodId": None,
                "term": {"id": "unknown-term", "uniqueName": "UNKNOWN"},
            }
        )
        normalized = normalize_game(parse_game(raw))
        self.assertEqual(normalized.unknown_stat_terms, ["unknown-term"])

    def test_score_mismatch_marks_loaded_source_record_partial(self):
        session = FakeSession()
        client = Mock()
        client.fetch_and_snapshot.return_value = ({"data": {}}, "/tmp/snapshot.json")
        roster_cache = Mock()
        parsed = SimpleNamespace(
            scores=[SimpleNamespace(teamId="team-1", team=None)],
            stats=[],
            date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        normalized = SimpleNamespace(
            has_two_team_scores=True,
            has_terms=True,
            has_roster=True,
            unknown_stat_terms=[],
            player_stat_row_count=5,
            is_ended=True,
            parse_failures=0,
            orphan_stat_athletes=[],
            fallback_resolved_athletes=[],
            points_mismatch=True,
            content_hash="hash",
        )
        with (
            patch.object(scraper.db, "create_source_record", return_value="record-1"),
            patch.object(scraper, "parse_game", return_value=parsed),
            patch.object(scraper, "normalize_game", return_value=normalized),
            patch("pipeline.loader.load_game") as loader,
        ):
            result = scraper._process_game(
                client,
                session,
                "game-1",
                "season-1",
                roster_cache,
            )
        self.assertEqual(result.status, "loaded")
        self.assertTrue(result.points_mismatch)
        self.assertIn("official score", result.note)
        self.assertEqual(loader.call_args.kwargs["load_status"], "partial")


class SnapshotPersistenceTests(unittest.TestCase):
    def test_local_snapshot_returns_local_path(self):
        with tempfile.TemporaryDirectory() as directory:
            client = MsportsClient()
            with (
                patch.object(client, "post_graphql", return_value={"data": {"ok": True}}),
                patch.dict(os.environ, {"SNAPSHOT_DIR": directory}, clear=False),
                patch.dict(os.environ, {"SNAPSHOT_URI_PREFIX": ""}, clear=False),
            ):
                payload, reference = client.fetch_and_snapshot(
                    "Game", {"id": "game-1"}, "query", "game_game-1"
                )
            client.close()

            self.assertEqual(payload, {"data": {"ok": True}})
            self.assertTrue(reference.startswith(directory))
            self.assertTrue(os.path.exists(reference))

    def test_durable_prefix_is_stored_while_file_remains_local(self):
        with tempfile.TemporaryDirectory() as directory:
            client = MsportsClient()
            prefix = "github-actions://owner/repo/runs/42/attempts/1/artifacts/raw-snapshots"
            with (
                patch.object(client, "post_graphql", return_value={"data": {"ok": True}}),
                patch.dict(
                    os.environ,
                    {"SNAPSHOT_DIR": directory, "SNAPSHOT_URI_PREFIX": prefix},
                    clear=False,
                ),
            ):
                _, reference = client.fetch_and_snapshot(
                    "Game", {"id": "game-1"}, "query", "game_game-1"
                )
            client.close()

            filename = reference.rsplit("/", 1)[-1]
            self.assertTrue(reference.startswith(f"{prefix}/"))
            self.assertTrue(os.path.exists(os.path.join(directory, filename)))


class RefreshSelectionTests(unittest.TestCase):
    def test_incremental_selection_covers_all_policy_branches(self):
        now = datetime(2026, 1, 10, tzinfo=timezone.utc)
        schedule = [
            DiscoveredGame(id=name, date=now.isoformat(), is_ended=True, division_id="d")
            for name in ("new", "open", "recent", "date-fallback", "old")
        ]
        existing = {
            "open": {"is_ended": False, "last_changed_at": now - timedelta(days=30), "date": now},
            "recent": {"is_ended": True, "last_changed_at": now - timedelta(days=6), "date": now},
            "date-fallback": {"is_ended": True, "last_changed_at": None, "date": now - timedelta(days=7)},
            "old": {"is_ended": True, "last_changed_at": now - timedelta(days=8), "date": now},
        }
        selected = select_incremental(schedule, existing, now=now)
        self.assertEqual([game.id for game in selected], ["new", "open", "recent", "date-fallback"])


class LoaderTransactionTests(unittest.TestCase):
    def test_loader_rolls_back_when_a_write_fails(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        with patch("pipeline.loader._seed_season_min", side_effect=RuntimeError("write failed")):
            with self.assertRaisesRegex(RuntimeError, "write failed"):
                load_game(conn, Mock(season={}), "source-1", changed=True)
        cursor.execute.assert_not_called()
        conn.rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
