from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError, jwt as jose_jwt

from auth.jwt import ALGORITHM, create_access_token, create_refresh_token, decode_token


def test_access_token_round_trip_has_expected_claims():
    token = create_access_token("user-123", "a@b.com", "alice")
    claims = decode_token(token)

    assert claims["sub"] == "user-123"
    assert claims["email"] == "a@b.com"
    assert claims["username"] == "alice"
    assert claims["type"] == "access"
    assert claims["exp"] > claims["iat"]


def test_refresh_token_round_trip_has_expected_claims():
    token = create_refresh_token("user-123")
    claims = decode_token(token)

    assert claims["sub"] == "user-123"
    assert claims["type"] == "refresh"
    assert "email" not in claims
    assert claims["exp"] - claims["iat"] == pytest.approx(7 * 24 * 3600, abs=5)


def test_tampered_token_is_rejected():
    token = create_access_token("user-123", "a@b.com", "alice")
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(JWTError):
        decode_token(tampered)


def test_expired_token_is_rejected():
    now = datetime.now(timezone.utc)
    expired_claims = {
        "sub": "user-123",
        "jti": "some-jti",
        "type": "access",
        "iat": now - timedelta(minutes=30),
        "exp": now - timedelta(minutes=15),
    }
    import os

    expired_token = jose_jwt.encode(expired_claims, os.environ["JWT_SECRET_KEY"], algorithm=ALGORITHM)

    with pytest.raises(JWTError):
        decode_token(expired_token)


def test_token_signed_with_wrong_secret_is_rejected():
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "user-123",
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    forged = jose_jwt.encode(claims, "not-the-real-secret", algorithm=ALGORITHM)

    with pytest.raises(JWTError):
        decode_token(forged)
