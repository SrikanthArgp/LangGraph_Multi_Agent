"""initial_schema

Revision ID: a7f571ea1f94
Revises:
Create Date: 2026-07-02 16:36:32.138380

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7f571ea1f94'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.execute("""
        CREATE TABLE users (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            email           VARCHAR(255) UNIQUE NOT NULL,
            username        VARCHAR(100) UNIQUE NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_users_email ON users(email)")

    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER users_set_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE TABLE chat_sessions (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id         UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title           VARCHAR(500),
            is_archived     BOOLEAN      NOT NULL DEFAULT FALSE,
            last_message_at TIMESTAMPTZ,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id)")
    op.execute(
        "CREATE INDEX idx_chat_sessions_user_last_msg "
        "ON chat_sessions(user_id, last_message_at DESC NULLS LAST)"
    )
    op.execute(
        "CREATE INDEX idx_chat_sessions_active "
        "ON chat_sessions(user_id, is_archived, last_message_at DESC NULLS LAST)"
    )
    op.execute("""
        CREATE TRIGGER chat_sessions_set_updated_at
            BEFORE UPDATE ON chat_sessions
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    op.execute("""
        CREATE TABLE messages (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id  UUID        NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role        VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content     TEXT        NOT NULL,
            metadata    JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX idx_messages_session_id ON messages(session_id)")
    op.execute("CREATE INDEX idx_messages_session_created ON messages(session_id, created_at ASC)")

    op.execute("""
        CREATE TABLE refresh_tokens (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  VARCHAR(64) NOT NULL,
            issued_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at  TIMESTAMPTZ NOT NULL,
            revoked     BOOLEAN     NOT NULL DEFAULT FALSE,
            revoked_at  TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id)")
    op.execute("CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash)")
    op.execute(
        "CREATE INDEX idx_refresh_tokens_active ON refresh_tokens(user_id, revoked, expires_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS refresh_tokens")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TRIGGER IF EXISTS chat_sessions_set_updated_at ON chat_sessions")
    op.execute("DROP TABLE IF EXISTS chat_sessions")
    op.execute("DROP TRIGGER IF EXISTS users_set_updated_at ON users")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP TABLE IF EXISTS users")
