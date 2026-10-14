"""Argon2id password hashing (argon2-cffi defaults, RFC 9106 low-memory profile)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

_hasher = PasswordHasher()

# Verified against when a username does not exist, so response time does not reveal it.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def burn_verification_time(password: str) -> None:
    verify_password(_DUMMY_HASH, password)
