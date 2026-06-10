"""The three §12 acceptance tests — deterministic, self-contained (no DB):
J.Moss golden record, idempotency, and a simulated stat-change. No broader framework.

Run:  PYTHONPATH=pipeline/src pipeline/.venv/bin/python pipeline/tests/test_golden.py
(or with pytest)
"""

from __future__ import annotations

import copy
import json
import os

from pipeline.parser import parse_game
from pipeline.normalizer import normalize_game

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "golden_game_44a47063.json")
MOSS = "f250ba30-e95e-4f3f-a6d0-95fd0cd9ef91"


def _load() -> dict:
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _moss_line(ng) -> dict:
    un = {t["id"]: t["unique_name"] for t in ng.terms}
    ev: dict[str, int] = {}
    for pid, _tid, term, _per, val in ng.player_stats:
        if pid == MOSS:
            ev[un[term]] = ev.get(un[term], 0) + val

    def c(u: str) -> int:
        return ev.get(u, 0)

    fgm = c("BSKT_2PTM") + c("BSKT_3PTM") + c("BSKT_1PTM")
    fga = c("BSKT_2PTA") + c("BSKT_3PTA") + c("BSKT_1PTA")
    return {
        "FGM": fgm,
        "FGA": fga,
        "FG%": round(fgm * 100 / fga, 1) if fga else None,
        "FTM": c("BSKT_FTM"),
        "FTA": c("BSKT_FTA"),
        "PTS": 2 * c("BSKT_2PTM") + 3 * c("BSKT_3PTM") + c("BSKT_FTM") + c("BSKT_1PTM"),
        "TOTRB": c("BSKT_RO") + c("BSKT_RD"),
    }


def test_golden_jmoss():
    ng = normalize_game(parse_game(_load()))
    assert _moss_line(ng) == {
        "FGM": 18, "FGA": 26, "FG%": 69.2, "FTM": 12, "FTA": 17, "PTS": 48, "TOTRB": 8,
    }


def test_idempotency_deterministic():
    # Normalizing the same snapshot twice yields an identical hash and identical
    # aggregated rows — the basis for "an unchanged re-run writes no new rows".
    a = normalize_game(parse_game(_load()))
    b = normalize_game(parse_game(_load()))
    assert a.content_hash == b.content_hash
    assert sorted(a.player_stats) == sorted(b.player_stats)


def test_simulated_stat_change():
    # Add one extra made 2PT event for J.Moss; the normalized payload must change
    # (new hash) and his FGM/PTS must increase by exactly one made shot.
    base = normalize_game(parse_game(_load()))
    base_line = _moss_line(base)

    raw = _load()
    stats = raw["data"]["game"]["stats"]["nodes"]
    two_ptm = next(
        s for s in stats if s["athleteId"] == MOSS and s["term"]["uniqueName"] == "BSKT_2PTM"
    )
    raw["data"]["game"]["stats"]["nodes"].append(copy.deepcopy(two_ptm))

    changed = normalize_game(parse_game(raw))
    changed_line = _moss_line(changed)

    assert changed.content_hash != base.content_hash
    assert changed_line["FGM"] == base_line["FGM"] + 1
    assert changed_line["PTS"] == base_line["PTS"] + 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL TESTS PASSED")
