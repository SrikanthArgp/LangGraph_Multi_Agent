import pytest

pytestmark = pytest.mark.requires_db

EXPECTED_TABLES = {"users", "chat_sessions", "messages", "refresh_tokens"}
EXPECTED_TRIGGERS = {"users_set_updated_at", "chat_sessions_set_updated_at"}
EXPECTED_INDEXES = {
    "idx_users_email",
    "idx_chat_sessions_user_id",
    "idx_chat_sessions_user_last_msg",
    "idx_chat_sessions_active",
    "idx_messages_session_id",
    "idx_messages_session_created",
    "idx_refresh_tokens_user_id",
    "idx_refresh_tokens_token_hash",
    "idx_refresh_tokens_active",
}


def test_select_1(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)


def test_pgcrypto_extension_enabled(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'pgcrypto'")
        assert cur.fetchone() is not None


def test_application_tables_exist(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        tables = {row[0] for row in cur.fetchall()}
    assert EXPECTED_TABLES <= tables


def test_updated_at_triggers_exist(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT trigger_name FROM information_schema.triggers WHERE trigger_schema = 'public'"
        )
        triggers = {row[0] for row in cur.fetchall()}
    assert EXPECTED_TRIGGERS <= triggers


def test_indexes_exist(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        indexes = {row[0] for row in cur.fetchall()}
    assert EXPECTED_INDEXES <= indexes
