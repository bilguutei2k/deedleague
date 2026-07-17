"""Static configuration + the two approved seeds (see docs/step1-source-shape-probe.md)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

PARSER_VERSION = "1"
SOURCE_NAME = "msports"
GRAPHQL_URL = os.environ.get("MSPORTS_GRAPHQL_URL", "https://stats-api.msports.mn/graphql")

# The parent league + the two approved seasons (verified during Step 1 discovery).
PARENT_LEAGUE_ID = "1c2152e7-32c1-4631-9764-ef2cf03e6d0b"
APPROVED_SEASON_IDS = (
    "07e2a69c-9648-44b3-8ddd-82cc2b22aaf3",  # 2025-2026 ОНЫ УЛИРАЛ
    "91748946-7b93-4a9f-bf63-5df9142e032d",  # 2024-2025 ОНЫ УЛИРАЛ
)

# Only the men's division ("ЭРЭГТЭЙ") is ingested in v1; women's is excluded.
MENS_DIVISION_NAME = "ЭРЭГТЭЙ"


@dataclass(frozen=True)
class PolitenessConfig:
    requests_per_second: float = 1.5
    concurrency: int = 4
    max_retries: int = 4
    backoff_seconds: float = 1.0


def database_url() -> str:
    url = (
        os.environ.get("PIPELINE_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("SUPABASE_DB_URL")
    )
    if not url:
        raise RuntimeError("PIPELINE_DATABASE_URL is not set")
    return url


def snapshot_dir() -> str:
    return os.environ.get("SNAPSHOT_DIR") or os.path.join(
        os.path.dirname(__file__), "..", "..", ".snapshots"
    )


def snapshot_uri_prefix() -> str | None:
    """Optional durable URI prefix corresponding to the local snapshot directory."""
    value = os.environ.get("SNAPSHOT_URI_PREFIX", "").strip()
    return value.rstrip("/") or None
