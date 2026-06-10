"""Incremental selection logic (§7.3).

A game is selected for an incremental run if ANY of:
  - New: in the schedule, not yet in `games`.
  - Not final: stored `is_ended = false`.
  - Recently changed: stored `is_ended = true` AND the freshness window covers it
    (`last_changed_at` within RECENT_DAYS; if null, fall back to the game `date`).
The 7-day window is a freshness optimization; the weekly full-resync is the safety net.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .discovery import DiscoveredGame

RECENT_DAYS = 7


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def select_incremental(
    schedule: list[DiscoveredGame],
    existing: dict[str, dict],
    now: datetime | None = None,
) -> list[DiscoveredGame]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RECENT_DAYS)
    selected: list[DiscoveredGame] = []
    for g in schedule:
        stored = existing.get(g.id)
        if stored is None:
            selected.append(g)  # new
            continue
        if not stored["is_ended"]:
            selected.append(g)  # not final
            continue
        # ended: recently changed?
        ref = _aware(stored.get("last_changed_at")) or _aware(stored.get("date"))
        if ref is not None and ref >= cutoff:
            selected.append(g)
    return selected
