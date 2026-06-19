"""v0012 - replace stored bearer session tokens with SHA-256 digests."""
import hashlib
import sqlite3


def _hash_token(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def up(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, session_token FROM user_sessions"
    ).fetchall()
    for row in rows:
        token = row["session_token"]
        if token.startswith("sha256:"):
            continue
        conn.execute(
            "UPDATE user_sessions SET session_token=? WHERE id=?",
            (_hash_token(token), row["id"]),
        )
