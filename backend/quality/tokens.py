"""Service-token guard for the Mac-side predict-agent endpoints.

No user session is involved: the caller is a long-running agent on the
operator's machine, authenticated with a shared secret from the environment.
"""
import secrets
from typing import Any, Optional

from fastapi import Header, HTTPException

from backend import config


def parse_bearer_token(raw: Any) -> Optional[str]:
    """Extract the credential from an Authorization header.

    Never raises: a non-string, empty, schemeless, or credential-less header
    simply yields None so the caller answers 401 instead of 500.
    """
    if not isinstance(raw, str):
        return None
    parts = raw.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def require_ingest_token(authorization: Optional[str] = Header(default=None)) -> None:
    """503 when the feature is unconfigured, 401 when the token does not match."""
    expected = config.DQCHECK_INGEST_TOKEN
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "prediction_ingest_disabled",
                "message": "DQCHECK_INGEST_TOKEN is not configured on this instance.",
            },
        )
    provided = parse_bearer_token(authorization)
    if provided is None or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_ingest_token",
                "message": "Invalid prediction ingest credentials.",
            },
        )
