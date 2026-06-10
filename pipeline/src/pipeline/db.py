"""psycopg connection helper + source_records provenance writes (DML only)."""

from __future__ import annotations

import json
from typing import Any

import psycopg

from .config import PARSER_VERSION, SOURCE_NAME, database_url


def connect() -> psycopg.Connection:
    # autocommit off: loads are explicit transactions.
    # prepare_threshold=None disables server-side prepared statements so the loader
    # works through Supabase's transaction-mode pooler (pgbouncer) as well as a direct conn.
    # TCP keepalives keep the connection alive across the polite per-request throttle so
    # the pooler/NAT does not drop a long-running backfill mid-flight.
    return psycopg.connect(
        database_url(),
        autocommit=False,
        prepare_threshold=None,
        keepalives=1,
        keepalives_idle=20,
        keepalives_interval=10,
        keepalives_count=5,
    )


class Session:
    """Lazily (re)connecting DB session. Reconnects after a dropped connection so a
    transient pooler disconnect doesn't abort a long backfill."""

    def __init__(self) -> None:
        self._conn: psycopg.Connection | None = None

    @property
    def conn(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = connect()
        return self._conn

    def reset(self) -> None:
        try:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
        except Exception:
            pass
        self._conn = None

    def close(self) -> None:
        self.reset()


def create_source_record(
    conn: psycopg.Connection,
    *,
    source_url: str,
    operation_name: str,
    variables: dict[str, Any],
    raw_snapshot_path: str | None,
    entity_type: str,
    entity_id: str,
) -> str:
    """Insert a provenance row (load_status='pending') and commit it immediately,
    so provenance survives even if the subsequent load fails."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_records
              (source_name, source_url, operation_name, variables, raw_snapshot_path,
               parser_version, entity_type, entity_id, load_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING id
            """,
            (
                SOURCE_NAME,
                source_url,
                operation_name,
                json.dumps(variables),
                raw_snapshot_path,
                PARSER_VERSION,
                entity_type,
                entity_id,
            ),
        )
        record_id = cur.fetchone()[0]
    conn.commit()
    return str(record_id)


def set_load_status(conn: psycopg.Connection, source_record_id: str, status: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE source_records SET load_status = %s WHERE id = %s",
            (status, source_record_id),
        )
    conn.commit()
