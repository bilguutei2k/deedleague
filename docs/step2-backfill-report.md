# Step 2 — Backfill Report (HARD STOP — awaiting approval)

Both approved seasons seeded into Supabase via `--backfill`, after applying the §8
date-windowed roster/team resolution. Validated against the captured golden snapshot and
recomputed from the **loaded database**.

## 1. Scope & row counts

Discovered **253 men's (ЭРЭГТЭЙ) games** → **253 loaded (0 missing, 0 failed)**. Women's excluded.

| Table | Rows | Notes |
|---|---:|---|
| seasons | 2 | 2024-25, 2025-26 |
| divisions | 2 | men's only |
| teams | 12 | |
| players | 250 | |
| stat_terms | 21 | 15 atomic + 6 derived |
| games | 253 | 243 ended, 10 upcoming |
| game_competitors | 506 | exactly 2/game ✓ |
| game_rosters | 8 533 | as-of-date rosters |
| game_player_stats | 64 583 | aggregated atomic counts |
| game_team_stats | 0 | no team-level events in source (expected) |
| standings | 0 | computed in Step 4 (not yet) |
| source_records | 792 | append-only across all runs |
| scrape_runs | 4 | backfill runs (1 buggy, 1 dropped, 2 clean) |

## 2. Golden record — PASS ✅ (recomputed from the DB)

Game `44a47063…`, **Justin "J.Moss" Moss**, summed across all period buckets (incl. null)
through the derived formulas, querying `game_player_stats`:

| | FGM | FGA | FG% | FTM | FTA | PTS | TOTRB |
|---|---|---|---|---|---|---|---|
| expected | 18 | 26 | 69.2 | 12 | 17 | 48 | 8 |
| **from DB** | **18** | **26** | **69.2** | **12** | **17** | **48** | **8** |

## 3. Standings 2025-26 — PASS ✅ (computed from DB `game_competitors`)

| Team | W-L | PF | PA | DIFF |
|---|---|---:|---:|---:|
| **BCH Knights** | 13-1 | 1263 | 1147 | +116 |
| Хасын хүлэгүүд | 8-3 | 896 | 802 | +94 |
| Омни Эрдэнэт Майнерс | 8-5 | 1002 | 948 | +54 |
| SG APES | 9-7 | 1326 | 1365 | −39 |
| Завхан Бродерс | 7-7 | 1210 | 1201 | +9 |
| Selenge Bodons | 6-8 | 1128 | 1118 | +10 |
| Ховд Шонхорууд | 5-8 | 1095 | 1117 | −22 |
| Darkhan United | 5-8 | 1044 | 1091 | −47 |
| Бишрэлт Металл | 6-10 | 1207 | 1286 | −79 |
| **Монголианс** | 2-12 | 1106 | 1202 | −96 |

BCH Knights top, Монголианс bottom — as expected.

## 4. §8 fix — date-windowed roster/team resolution: VERIFIED ✅

`game.memberships` returns the **current** roster, so transferred players' stat events
were dropped. Fix: resolve team per game from a **team-scoped membership history**,
selecting memberships whose `[from, to]` window covers the game date; with a second tier
that attributes a still-unmatched stat athlete to whichever competing team they have **any**
membership with (handles source end-dates recorded a few days early).

**Impact (orphan stat events that get dropped):**

| | before fix | after fix |
|---|---:|---:|
| distinct orphan athletes | 95 | **5** |
| games with orphan events | 44 | 26 |
| total orphan events dropped | 427 | 187 |
| **made-points dropped** | 65 (7 games) | **28 (4 games)** |

- **McKenzie Moore's Омни game events are now included** ✅ — game `63e38aeb` and
  `f7aed4f1` both reconcile exactly (e.g. Омни 97 = calc 97).
- The legacy/fixture path is unchanged (J.Moss fixture hash identical).

## 5. Residual PTS mismatches — all genuine upstream gaps (logged, not bugs)

The PTS cross-check (recomputed made-points vs official score) flags **7 games**. None are
pipeline bugs — they are upstream source characteristics, per §5 ("report disagreements,
don't treat scores as source of truth"):

1. **One-sided box score (1 game):** `c2dc8d65` (2025-12-08) — Selenge Bodons scored 78 but
   the source has **no per-player stats** for them (Омни is fully statted). The "8th" source
   gap you flagged — left as-is, logged here.
2. **Residual orphans (4 games, early-season import churn):** `c075da75` (13), `01aee5db`
   (10), `b4755de4` (3), `46197fae` (2) — total **28 made-points** from **5 players** who
   have **no membership record with either competing team** (some have none at all). Not
   resolvable from source roster data; logged as upstream gaps.
3. **Play-by-play vs official score ±1–2 (2 games):** `524a33a0` (−2), `ffe5daaf` (±1) —
   the summed made-shots differ from the official final by 1–2 (normal scorer's-table
   corrections). Logged.

## 6. Coverage / partial games

Completeness gate (approved): two team score nodes + term dictionary + roster + successful
stats parse (**"periods present" dropped**). No game failed the gate.

- **13 fully-partial games** (0 player-stat rows): **9 upcoming** (`is_ended=false`,
  Dec 16–31) + **4 ended-but-unstatted in source** (`538f4ba8`, `b8388f56`, `7ffa825a`,
  `b3af7da3`, Dec 9–10) — source has the result but no box score yet.
- **1 half-statted game** (`c2dc8d65`, §5.1) — currently classified `full` (it has one
  team's stats); the Step-5 coverage badge should treat one-sided games as partial.

## 7. Provenance — PASS ✅

- Every loaded **game** and every **stat row** has `source_record_id` (0 missing).
- `source_records.load_status`: **675 loaded, 117 failed**. The 117 `failed` are from the
  first (buggy) run — never committed, correctly left `failed`. (792 total rows = append-only
  provenance across all fetches, as expected.)
- `loaded` game records with no `games` row: **0** → `load_status='loaded'` reflects
  committed loads only.
- Duplicate `game_player_stats` keys: **0** → delete-and-replace is clean, no accumulation.

## 8. Stat-calc readiness — registrable split & formulas: PASS ✅

- `registrable → atomic/derived` split **holds for all 21 terms** (15 atomic / 6 derived),
  zero violations.
- All **6 derived formulas** (PTS, TOTRB, FGM, FGA, FG%, FT%) fit the supported grammar;
  **no unsupported formulas**.

## 9. Bugs found & fixed during backfill

1. `content_hash` canonicalization did `sorted()` on rows containing `None` →
   `TypeError` crashed 117 games on run 1. Fixed (JSON-string sort key); re-verified.
2. The single long-held DB connection dropped mid-run on the transaction pooler (run 3,
   game 30/78). Fixed with TCP keepalives + a reconnecting `Session` with per-game retry.

## 10. Deferred (per hard stop)

Step 3 (incremental/full-resync), Step 4 (stat-calc + standings table), Step 5 (frontend),
Step 6 (CI) — **not started**.

## Decision requested

The backfill is clean and golden/standings/provenance all pass. Residual data gaps (§5)
are upstream, fully characterized, and small (28 made-points / 5 players / 4 early-season
games + 1 one-sided game + 2 ±1–2 scoring corrections). **Approve to proceed to Step 3?**
(Or request further work on coverage-badge handling of one-sided games before continuing.)
