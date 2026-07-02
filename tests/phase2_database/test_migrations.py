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


def test_orm_models_match_live_schema(pg_sync_engine):
    """Fails if a model is changed without a matching Alembic revision."""
    with pg_sync_engine.connect() as conn:
        migration_context = MigrationContext.configure(conn)
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
