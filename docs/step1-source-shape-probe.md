# Step 1 — Source-Shape Probe Report

Read-only probe of the msports GraphQL API (`https://stats-api.msports.mn/graphql`),
run during the build. No auth used (empty/absent `authorization` → 200 with full data).
All raw responses captured; the golden game snapshot is committed at
`pipeline/tests/fixtures/golden_game_44a47063.json`.

## 1. Discovery — entity hierarchy

Introspection (`__schema`) is **enabled** — the §5 HTML-scrape fallback is NOT needed.

```
Tournament (= "competition"/season)
  └─ Division        (men "ЭРЭГТЭЙ" / women "ЭМЭГТЭЙ")
       └─ Game
            ├─ scores       (2 nodes, one per competing team)
            ├─ periods      (0 OR 4 nodes — see §4)
            ├─ memberships  (per-game roster, ~15–19 per team)
            └─ stats        (atomic per-event records)
```

Root query fields used: `tournament(where)`, `games(where:{division:{tournamentId:{equals}}})`,
`game(where:{id})`. Schedule query `games(...)` exposes `id`, `date`, `isEnded`, `divisionId`
— satisfies the §5 minimum (game_id, division_id, date, +isEnded).

## 2. Seasons — count verified, NO STOP condition

Parent league `1c2152e7-32c1-4631-9764-ef2cf03e6d0b` = **'ҮНДЭСНИЙ ДЭЭД ЛИГ'** has
**exactly 2 child seasons**, matching the two approved seeds:

| Season  | Tournament id (seasons.id)             | Dates                  | Divisions |
|---------|----------------------------------------|------------------------|-----------|
| 2025-26 | `07e2a69c-9648-44b3-8ddd-82cc2b22aaf3` | 2025-10-01 .. 2026-05-31 | ЭРЭГТЭЙ, ЭМЭГТЭЙ |
| 2024-25 | `91748946-7b93-4a9f-bf63-5df9142e032d` | 2024-10-12 .. 2025-06-01 | ЭРЭГТЭЙ, ЭМЭГТЭЙ |

Discovery returned **2** seasons → proceed (no extra seasons → no STOP).

## 3. ⚠️ Men-only scoping decision

Each season exposes a **women's division (ЭМЭГТЭЙ)** in addition to men's (ЭРЭГТЭЙ).
The plan is the **men's** league only ("Mongolia's top *men's* basketball league").
**Decision:** ingest ONLY the ЭРЭГТЭЙ division per season; deliberately exclude ЭМЭГТЭЙ in v1.
The golden game's division is ЭРЭГТЭЙ, consistent with this scope.

Men's-division ids (the only divisions we ingest):
- 2024-25 men: `4ed00fd8-5175-46d0-9b09-cdd9eabe6c8a`
- 2025-26 men: `669530f1-9d8d-4a6e-9e55-42450200b2af`

Men's schedule sizes (backfill scope):
- 2024-25: **175 games**, all `isEnded=true` (2024-10-12 .. 2025-05-21).
- 2025-26: **78 games**, 68 ended / 10 upcoming (2025-10-01 .. ongoing).
- **Total ≈ 253 games.**

## 4. Stat semantics — confirmed against schema + data

**Atomic grain.** `stats.nodes[]` are raw per-event records, no event id. Aggregate by counting:
- player → `(game_id, athlete_id, team_id, term_id, period_id)`
- team → `(game_id, team_id, term_id, period_id)`

**Routing (schema-confirmed nullability):** `Stat.athleteId` nullable, `teamId` nullable,
`periodId` nullable, `termId` NOT NULL.
- `athleteId` present → player stat.
- `athleteId` null & `teamId` present → team stat.
- neither → parse failure (recorded, not dropped).

**Observed in 11-game scan + golden game:** **every** event had `athleteId` set.
**Team-level events = 0, parse-failures = 0** across both seasons. ⇒ `game_team_stats`
(from athleteId-null events) is **empty in v1 data**; team box totals are *computed* by
aggregating player stats (Step 4). The routing/parse-failure logic is still implemented defensively.

**Periods are sparse and inconsistent — KEY FINDING:**
- Golden game `44a47063` has **0 periods**; another 2024-25 game has **4 periods**.
- Period-distribution over scan: `{4 periods: 5 games, 0 periods: 6 games}`.
- In a 4-period game, stats split **179 null-period + 699 period-tagged** events (0 orphans).
  ⇒ §5 rule confirmed: game total = sum over **all** buckets *including the null bucket*,
  exactly once. Summing only period buckets would silently drop the null-bucket events.
- `period_id` is stored as a raw nullable bucket key on the stat rows (uniqueness uses
  `NULLS NOT DISTINCT`). **No `periods` dimension table** (not in §6; period names unused in v1).

**⚠️ Completeness-gate conflict (needs your decision — Step 3, after the hard stop):**
§7.6 lists "**periods present**" as a hard requirement for a complete snapshot, but the §9
coverage "full" definition does NOT mention periods, and **the golden FULL game has 0 periods**.
Taken literally, "periods present" would mark the golden game (and ~half of all games) `failed`.
**Recommendation:** drop "periods present" from the completeness gate; align it with the §9
"full" definition (2 team scores *with values*, roster, term dictionary, ≥1 parsed stat row).
Periods become informational, not gating. Flagged here; not yet implemented.

## 5. Scores — validation-only, values can be empty

`scores.nodes[]` = 2 nodes (one per team), each `{ order, value, isWinner, competitorType, teamId }`.
- `Score.value` is a **nullable String** and can be `''` (empty) for **upcoming/unplayed** games
  (observed: game `a981ea08`, `stats=0`, `scores=['','']`, roster present).
- Parser: `value` empty/null → points `null`; never crash. Used only to cross-check recomputed PTS.
- `order` (0/1) is the **competitor_order**. **Home/away is NOT exposed** — stored as raw order,
  rendered "Team A / Team B". (League plays at one venue; not asserted.)

## 6. Roster / memberships

`game.memberships.nodes[]` = the per-game roster (the two teams' active memberships).
- ~15–19 per team; **no duplicate `(team, athlete)`** within a game ⇒ `game_rosters` PK
  `(game_id, player_id, team_id)` is safe.
- `Membership.number` (jersey) is **nullable** and lives on `game_rosters`, not `players`.
- Some rostered players have **0 stat events** → still get a roster row (zeros in box score), per §5.

## 7. Term dictionary — 21 terms, atomic/derived split holds

`registrable=true & formula=null` → **atomic** (source-recorded events).
`registrable=false & formula=<expr>` → **derived** (computed). The §8 `registrable` hypothesis
**holds** for all 21 terms in both seasons.

Atomic (15): `BSKT_2PTM/2PTA, 3PTM/3PTA, FTM/FTA, RO, RD, AS, ST, BS, TO, PF`, plus
`GENERAL_IN/GENERAL_OUT` (substitutions, `showOnUser=false`).

Derived (6):
| short | uniqueName | formula |
|-------|------------|---------|
| PTS   | BSKT_PTS   | `{BSKT_2PTM}*2+{BSKT_3PTM}*3+{BSKT_FTM}*1+{BSKT_1PTM}*1` |
| TOTRB | BSKT_TOTRB | `{BSKT_RO}*1+{BSKT_RD}*1` |
| FGM   | BSKT_FGM   | `{BSKT_1PTM}+{BSKT_2PTM}+{BSKT_3PTM}` |
| FGA   | BKST_FGA   | `{BSKT_1PTA}*1+{BSKT_2PTA}*1+{BSKT_3PTA}*1` |
| FG%   | BSKT_FG    | `({BSKT_1PTM}+{BSKT_2PTM}+{BSKT_3PTM})*100/({BSKT_1PTA}+{BSKT_2PTA}+{BSKT_3PTA})` |
| FT%   | BSKT_FT    | `{BSKT_FTM}*100/({BSKT_FTA})` |

**Formula grammar (the ONLY syntax to implement, per §8):** `{TERM}` references,
integer literals, operators `+ - * /`, parentheses. **A referenced term not present in the
recorded counts resolves to 0** — e.g. `BSKT_1PTM`/`BSKT_1PTA` are referenced but absent from the
dictionary; treating them as 0 reproduces the golden record exactly. Division-by-zero → `null` (render `—`).

> Note: `uniqueName` is schema-nullable and one term has a typo (`BKST_FGA`). Keys are term **UUIDs**,
> never uniqueName strings. Required leader/display stats are mapped from confirmed term IDs.

## 8. Golden record — PASS ✅

Game `44a47063-82c6-4c75-a096-074ca6bdb473` (2024-25), player **Justin "J.Moss" Moss**
(`f250ba30-…`), computed from the captured snapshot via the formula engine:

| FGM | FGA | FG% | FTM | FTA | PTS | TOTRB |
|-----|-----|-----|-----|-----|-----|-------|
| 18  | 26  | 69.2| 12  | 17  | 48  | 8     |

Matches the §12 expected values exactly. (Raw atomic counts: 2PTM=18, 2PTA=26, 3PTM/3PTA=0,
FTM=12, FTA=17, RO=2, RD=6, AS=1, ST=1, BS=2, TO=2, PF=5.)

> Name fields are **inverted** vs Western order: API `name="Moss"` (family), `surname="Justin"`
> (given). Stored **as-returned** per §2; "J.Moss" display = surname-initial + name (display layer, later).

## 9. Schema-affecting decisions carried into the Drizzle schema

1. `game_team_stats` table built but empty in v1 data (defensive routing only).
2. `period_id` = raw nullable bucket key on stat rows; **no `periods` table**; uniqueness
   `NULLS NOT DISTINCT`.
3. **NEW table `game_competitors`** (flagged for approval): §6 says "store competitor_order info
   via the scores parse" but lists no column for it, while standings (W/L, PF/PA) and the PTS
   cross-check need the per-team final points + order. Added `game_competitors(game_id, team_id,
   competitor_order, points, is_winner)` — 2 rows/game. This is the only structural addition beyond §6.
4. Minor additive columns: `seasons.parent_league_id` (lineage), and display metadata on
   `stat_terms` (`name`, `term_type`, `order_index`, `show_on_user`, `is_default`) — the §6
   conflict-check still keys on `unique_name/formula/registrable`.
