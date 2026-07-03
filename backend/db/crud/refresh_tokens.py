import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RefreshToken


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create(
    db: AsyncSession, user_id: uuid.UUID, token: str, expires_at: datetime
) -> RefreshToken:
    row = RefreshToken(user_id=user_id, token_hash=hash_token(token), expires_at=expires_at)
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def get_active_by_token(db: AsyncSession, token: str) -> RefreshToken | None:
    """Non-revoked, non-expired lookup by raw token - hashed before querying since only the
    hash is stored (setup/db_setup.md: token_hash is SHA-256 hex of the raw JWT string).
    """
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_token(token),
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()


async def revoke(db: AsyncSession, row: RefreshToken) -> RefreshToken:
    row.revoked = True
    row.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(row)
    return row
