from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

import db.models  # noqa: F401  (registers all tables on Base.metadata)
from db.base import Base

pytestmark = pytest.mark.requires_db

REPO_ROOT = Path(__file__).resolve().parents[2]

# Created by langgraph-checkpoint-postgres's AsyncPostgresSaver.setup() (Phase 6's
# api/main.py lifespan), not by Alembic - plan.md documents these as "managed automatically...
# do not create manually" and deliberately has no ORM model for them. They exist in the live
# DB from here on (idempotent setup(), never dropped), so the schema-diff below must ignore
# them rather than flag them as drift every time this test runs.
_LANGGRAPH_MANAGED_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


def _include_name(name: str, type_: str, _parent_names: dict) -> bool:
    if type_ == "table" and name in _LANGGRAPH_MANAGED_TABLES:
        return False
    return True


def test_orm_models_match_live_schema(pg_sync_engine):
    """Fails if a model is changed without a matching Alembic revision."""
    with pg_sync_engine.connect() as conn:
        migration_context = MigrationContext.configure(conn, opts={"include_name": _include_name})
        diff = compare_metadata(migration_context, Base.metadata)
    assert diff == [], f"ORM models are out of sync with the live schema: {diff}"


def test_alembic_history_has_single_head():
    config = Config(str(REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1


def test_live_db_stamped_at_latest_head(pg_conn):
    config = Config(str(REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    (expected_head,) = script.get_heads()

    with pg_conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        (actual_version,) = cur.fetchone()

    assert actual_version == expected_head
