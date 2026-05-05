"""Password hashing, session token generation, IP hashing.

Routes and session storage live in `backend/users/` (Package 2).
"""
import hashlib
import secrets
import bcrypt


def hash_password(plain: str) -> str:
    """Hash a password using bcrypt (work factor 12)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time password verification. Returns False on any error."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_session_token() -> str:
    """URL-safe random token (43 chars from 32 random bytes)."""
    return secrets.token_urlsafe(32)


def hash_ip(ip: str) -> str:
    """SHA-256 hex digest of an IP address. Used for privacy-preserving session logging."""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()
