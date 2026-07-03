from sqlalchemy import CheckConstraint

from db.base import Base
from db.models import ChatSession, Message, RefreshToken, User


def test_all_tables_registered_on_base_metadata():
    assert set(Base.metadata.tables) == {"users", "chat_sessions", "messages", "refresh_tokens"}


def test_users_table_columns():
    cols = {c.name: c for c in User.__table__.columns}
    assert set(cols) == {
        "id",
        "email",
        "username",
        "hashed_password",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert cols["email"].unique
    assert cols["username"].unique
    assert not cols["hashed_password"].nullable
    assert not cols["is_active"].nullable


def test_users_email_index_present():
    index_names = {i.name for i in User.__table__.indexes}
    assert "idx_users_email" in index_names


def test_chat_sessions_columns_and_foreign_key():
    cols = {c.name: c for c in ChatSession.__table__.columns}
    assert set(cols) == {
        "id",
        "user_id",
        "title",
        "is_archived",
        "last_message_at",
        "created_at",
        "updated_at",
    }
    assert cols["title"].nullable
    assert not cols["is_archived"].nullable

    fk = next(iter(cols["user_id"].foreign_keys))
    assert fk.column.table.name == "users"
    assert fk.ondelete == "CASCADE"


def test_chat_sessions_indexes_present():
    index_names = {i.name for i in ChatSession.__table__.indexes}
    assert index_names == {
        "idx_chat_sessions_user_id",
        "idx_chat_sessions_user_last_msg",
        "idx_chat_sessions_active",
    }


def test_messages_role_check_constraint():
    check_constraints = [
        c for c in Message.__table__.constraints if isinstance(c, CheckConstraint)
    ]
    assert any(c.name == "messages_role_check" for c in check_constraints)


def test_messages_metadata_attr_maps_to_metadata_column():
    assert Message.metadata_.property.columns[0].name == "metadata"
    assert "metadata" in Message.__table__.columns


def test_messages_foreign_key_cascades_on_delete():
    fk = next(iter(Message.__table__.c.session_id.foreign_keys))
    assert fk.column.table.name == "chat_sessions"
    assert fk.ondelete == "CASCADE"


def test_refresh_tokens_columns_and_foreign_key():
    cols = {c.name: c for c in RefreshToken.__table__.columns}
    assert set(cols) == {
        "id",
        "user_id",
        "token_hash",
        "issued_at",
        "expires_at",
        "revoked",
        "revoked_at",
    }
    fk = next(iter(cols["user_id"].foreign_keys))
    assert fk.column.table.name == "users"
    assert fk.ondelete == "CASCADE"


def test_refresh_tokens_indexes_present():
    index_names = {i.name for i in RefreshToken.__table__.indexes}
    assert index_names == {
        "idx_refresh_tokens_user_id",
        "idx_refresh_tokens_token_hash",
        "idx_refresh_tokens_active",
    }


def test_relationships_wired_both_directions():
    assert User.sessions.property.mapper.class_ is ChatSession
    assert ChatSession.user.property.mapper.class_ is User
    assert ChatSession.messages.property.mapper.class_ is Message
    assert Message.session.property.mapper.class_ is ChatSession
    assert User.refresh_tokens.property.mapper.class_ is RefreshToken
    assert RefreshToken.user.property.mapper.class_ is User
