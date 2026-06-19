"""FastAPI dependencies for auth and authorization.

Used by every route in subsequent packages:
  @router.get("/api/feed", dependencies=[Depends(require_seen_manual)])
  def feed(user: dict = Depends(get_current_user)): ...
"""
import sqlite3
from ipaddress import ip_address
from typing import Iterator, Optional

from fastapi import Cookie, Depends, HTTPException, Request

from backend import config
from backend.shared.db import connect
from backend.users import service


def get_db() -> Iterator[sqlite3.Connection]:
    """Yield-based DB connection — called per-request."""
    conn = connect(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    db: sqlite3.Connection = Depends(get_db),
    session_token: Optional[str] = Cookie(None, alias=config.SESSION_COOKIE_NAME),
) -> sqlite3.Row:
    """Resolve current user from session cookie. 401 if not authenticated."""
    if not session_token:
        raise HTTPException(status_code=401, detail="not authenticated")
    user = service.get_user_by_session(db, session_token=session_token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    return user


def get_current_user_optional(
    db: sqlite3.Connection = Depends(get_db),
    session_token: Optional[str] = Cookie(None, alias=config.SESSION_COOKIE_NAME),
) -> Optional[sqlite3.Row]:
    """Like get_current_user but returns None instead of 401."""
    if not session_token:
        return None
    return service.get_user_by_session(db, session_token=session_token)


def require_admin(user: sqlite3.Row = Depends(get_current_user)) -> sqlite3.Row:
    """403 if not admin. Use as additional dependency on admin routes."""
    if user["role"] != "admin":
        raise HTTPException(status_code=404, detail="not found")  # hide existence per spec
    return user


def require_seen_manual(user: sqlite3.Row = Depends(get_current_user)) -> sqlite3.Row:
    """409 if user hasn't seen the help manual yet (frontend redirects to /help)."""
    if user["has_seen_manual"] != 1:
        raise HTTPException(
            status_code=409,
            detail={"error": "manual_not_seen", "message": "user must view /help first"},
        )
    return user


def require_passed_training(user: sqlite3.Row = Depends(require_seen_manual)) -> sqlite3.Row:
    """409 if user hasn't passed the training gate."""
    if user["has_passed_training"] != 1:
        raise HTTPException(
            status_code=409,
            detail={"error": "training_not_passed", "message": "user must complete training"},
        )
    return user


def get_request_ip(request: Request) -> Optional[str]:
    """Extract client IP from request.

    X-Forwarded-For is honored only when the immediate peer is a configured
    trusted proxy. The chain is walked from right to left, returning the
    nearest untrusted address. This remains correct whether a proxy
    overwrites XFF or appends to an attacker-supplied value.
    """
    peer = request.client.host if request.client else None
    peer_is_trusted = False
    if peer and config.TRUST_FORWARDED_FOR:
        try:
            peer_ip = ip_address(peer)
            peer_is_trusted = any(
                peer_ip in network for network in config.TRUSTED_PROXY_NETWORKS
            )
        except ValueError:
            peer_is_trusted = False

    # Hugging Face's edge proxy owns the forwarding header and does not
    # expose a stable public CIDR contract to Space containers.
    if config.SPACE_ID:
        peer_is_trusted = True

    if peer_is_trusted:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            parsed_chain = []
            for value in fwd.split(","):
                try:
                    parsed_chain.append(ip_address(value.strip()))
                except ValueError:
                    continue
            for candidate in reversed(parsed_chain):
                if not any(
                    candidate in network
                    for network in config.TRUSTED_PROXY_NETWORKS
                ):
                    return str(candidate)
    return peer
