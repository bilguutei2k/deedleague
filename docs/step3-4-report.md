# Steps 3 & 4 — Incremental Refresh + Stat-Calc (HARD STOP before Step 5)

Built on the clean Step-2 checkpoint (`0563ded`). All checks run against the live
Supabase database.

## Step 3 — Incremental + full-resync

One CLI, four selection paths (`pipeline/src/pipeline/cli.py`,`refresh.py`,`scraper.py`):
`--backfill` / `--full-resync` (every game), `--incremental` (§7.3 selection),
`--season`/`--game` (targeted). Change detection on `content_hash` decides load vs
touch-only. The completeness gate runs before any write.

### Acceptance checks (verified on the golden game in the live DB)

**A. Unchanged re-run writes zero new normalized rows — PASS ✅**
`--game 44a47063` after a load: `status=unchanged`; `game_player_stats` stayed at 198
rows; `last_fetched_at` advanced; `last_changed_at` unchanged; `content_hash` unchanged;
the new fetch appended one snapshot + one `source_records` row marked **`unchanged`**.

**B. Changed payload fully replaces the game's stat rows — PASS ✅**
Forcing change detection (corrupting the stored hash): `status=loaded`; rows back to 198
with **zero duplicate keys** (delete-and-replace); `last_changed_at` advanced; the real
`content_hash` was rewritten; J.Moss line intact (18 FGM).

**C. Completeness gate keeps existing good rows on a partial fetch — PASS ✅**
Injecting a partial snapshot (team score nodes stripped) for an already-complete game:
`status=failed` ("missing two team score nodes"); the 198 existing rows were **kept**;
`last_changed_at` unchanged; the fetch's `source_records.load_status` = `failed`. A later
partial pull cannot wipe a previously-complete game — this protects the 13 partials and
the one-sided game.

**Selection logic (§7.3) — PASS ✅** (unit-tested all branches): selects New, Not-final,
and Recently-changed (`last_changed_at` within 7 days; null → game `date`); excludes ended
games whose change/date is older than the window. The weekly full-resync remains the safety net.

### Timezone — verified

The source returns explicit **UTC** timestamps (`…Z`). Evidence: UTC game hours 03:00–12:00
map to **11:00–20:00 Asia/Ulaanbaatar** (UTC+8) — sensible tip-offs (peaks 18:00 & 20:00
local). Stored as `timestamptz` (UTC instant). The 7-day incremental window and cron compare
in **UTC**; Asia/Ulaanbaatar is a display-only concern (Step 5).

## Step 4 — Stat-calc + standings + aggregates

`pipeline/src/pipeline/statcalc.py`.

### Formula engine — PASS ✅
Implements ONLY the observed grammar: `{TERM}` refs, integer literals, `+ - * /`,
parentheses; a referenced term absent from the counts → 0; **division by zero → `None`**
(rendered "—"). Recursive-descent evaluator (no `eval`). Recomputed J.Moss derived line
matches the golden record **within ±0.05pp before display rounding**:

| FGM | FGA | FG% | FTM | FTA | PTS | TOTRB | FT% |
|---|---|---|---|---|---|---|---|
| 18 | 26 | 69.2 | 12 | 17 | 48 | 8 | 70.6 |

All 6 derived terms (PTS, TOTRB, FGM, FGA, FG%, FT%) are supported; no unsupported syntax.
(`3P%`/`2P%` have no term in the dictionary, so they are not displayed — validated "where the
term exists".) Percentages display to one decimal, half-up.

### Standings table — PASS ✅ (computed, not scraped)
`recompute_standings(season_id)` delete-and-replaces a season's rows from `game_competitors`
(decided games = points + winner present). Integrated into `run_ingest` (§7.9 recompute step).
2025-26 (10 teams):

| Team | W-L | PCT | PF | PA | DIFF |
|---|---|---|---:|---:|---:|
| **BCH Knights** | 13-1 | .929 | 1263 | 1147 | +116 |
| Хасын хүлэгүүд | 8-3 | .727 | 896 | 802 | +94 |
| Омни Эрдэнэт Майнерс | 8-5 | .615 | 1002 | 948 | +54 |
| SG APES | 9-7 | .563 | 1326 | 1365 | −39 |
| Завхан Бродерс | 7-7 | .500 | 1210 | 1201 | +9 |
| Selenge Bodons | 6-8 | .429 | 1128 | 1118 | +10 |
| Darkhan United | 5-8 | .385 | 1044 | 1091 | −47 |
| Ховд Шонхорууд | 5-8 | .385 | 1095 | 1117 | −22 |
| Бишрэлт Металл | 6-10 | .375 | 1207 | 1286 | −79 |
| **Монголианс** | 2-12 | .143 | 1106 | 1202 | −96 |

### SCORE-ONLY-GAME RULE (the data-correctness item) — implemented & stated

For games where a team has a final score but no per-player stats (the one-sided game
`c2dc8d65`, and the 4 ended-but-unstatted Dec 9–10 games):

1. **Standings, PF/PA, point-differential** come from `game_competitors` (the official
   scores). Such games **count normally** — the result is real; only the box score is
   missing. Verified: `c2dc8d65` counts in Selenge's 14 decided games (6-8 record).
2. **Per-player / per-team stat aggregates** sum `game_player_stats` and count only the
   games where that entity has stat rows; a no-stat game is excluded from its per-game
   denominators, so it never deflates averages. Verified: Selenge `statted_games=13 <
   decided_games=14`.
3. **Team "points scored" is always taken from `game_competitors`, never re-derived from
   summed player PTS** (which would undercount a score-only game). This is the consistent
   rule that prevents the one-sided game from distorting standings/diff/aggregates.

### Aggregates + chart hook
`player_season_line(season, player)` (atomic totals + derived line + statted games_played)
and `rolling_point_diff(season, team)` (cumulative differential per game, from scores) are
implemented for Step-5 read use. No ratings/Elo (hooks only, per scope).

## Tests
The three §12 tests still pass (`pipeline/tests/test_golden.py`): J.Moss fixture,
idempotency (deterministic normalize), simulated stat-change.

## Deferred to Step 5 (HARD STOP here)
- Frontend (pages, the one chart, coverage badges) — **not started**.
- Coverage-badge treatment of one-sided games as *partial* — still logged, for Step 5.
- Step 6 (GitHub Actions schedules) — **not started**.
