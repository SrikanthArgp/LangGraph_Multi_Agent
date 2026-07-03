import bcrypt

_MAX_BCRYPT_BYTES = 72


def hash_password(password: str) -> str:
    truncated = password.encode("utf-8")[:_MAX_BCRYPT_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    truncated = plain_password.encode("utf-8")[:_MAX_BCRYPT_BYTES]
    return bcrypt.checkpw(truncated, hashed_password.encode("utf-8"))
