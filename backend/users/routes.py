"""Auth + user routes."""
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from backend import config
from backend.gamification import service as gamification_service
from backend.gamification.models import ProfileResponse
from backend.shared import audit
from backend.shared.rate_limit import rate_limit
from backend.users import service
from backend.users.deps import (
    get_db, get_current_user, get_request_ip
)
from backend.users.models import (
    RegisterRequest, LoginRequest, UserOut, OkResponse,
)

router = APIRouter(prefix="/api", tags=["users"])


# Per-IP throttles. Generous-but-noticeable: a real user typing a wrong
# password ten times wakes up; an attacker brute-forcing the seeded
# admin password hits 429 long before bcrypt is the bottleneck. The
# in-memory sliding-window limiter is appropriate for the single-process
# uvicorn deployment; cross-host coordination is out of polish scope.
_login_throttle = rate_limit(
    namespace="auth.login",
    max_hits=10,
    window_seconds=5 * 60,
)
_register_throttle = rate_limit(
    namespace="auth.register",
    max_hits=5,
    window_seconds=60 * 60,
)


def _user_to_out(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "has_passed_training": bool(row["has_passed_training"]),
        "has_seen_manual": bool(row["has_seen_manual"]),
        "avatar_color": row["avatar_color"],
        "created_at": row["created_at"],
    }


@router.post("/auth/register", response_model=UserOut, status_code=201)
def register(
    payload: RegisterRequest,
    db: sqlite3.Connection = Depends(get_db),
    _throttle: None = Depends(_register_throttle),
):
    try:
        user_id = service.register(
            db,
            username=payload.username,
            password=payload.password,
            invite_code=payload.invite_code,
            email=payload.email,
        )
    except service.InvalidInviteCode as e:
        raise HTTPException(status_code=403, detail=str(e))
    except service.UsernameTaken as e:
        raise HTTPException(status_code=409, detail=str(e))
    except service.EmailTaken as e:
        raise HTTPException(status_code=409, detail=str(e))
    except service.InvalidPassword as e:
        raise HTTPException(status_code=422, detail=str(e))

    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _user_to_out(user)


@router.post("/auth/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: sqlite3.Connection = Depends(get_db),
    _throttle: None = Depends(_login_throttle),
):
    try:
        token = service.login(
            db,
            username=payload.username,
            password=payload.password,
            ip=get_request_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except service.InvalidCredentials as e:
        raise HTTPException(status_code=401, detail=str(e))
    except service.UserDisabled as e:
        raise HTTPException(status_code=401, detail=str(e))

    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 60 * 60,  # 30 days
        secure=config.is_production(),
        path="/",
    )
    return {"ok": True}


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: sqlite3.Connection = Depends(get_db),
):
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    if token:
        service.logout(db, session_token=token)
    response.delete_cookie(config.SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me", response_model=UserOut)
def me(user: sqlite3.Row = Depends(get_current_user)):
    return _user_to_out(user)


@router.post("/me/seen-manual", response_model=OkResponse)
def seen_manual(
    user: sqlite3.Row = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
):
    db.execute(
        "UPDATE users SET has_seen_manual=1, updated_at=datetime('now') WHERE id=?",
        (user["id"],),
    )
    return {"ok": True}


@router.get("/me/profile", response_model=ProfileResponse)
def get_my_profile(
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
):
    """Aggregated profile: identity + XP + streak + today counters + badges.
    Gated by get_current_user only (pre-training users see their zeroed state)."""
    state = gamification_service.get_profile_state(db, user_id=user["id"])
    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "avatar_color": user["avatar_color"],
        },
        **state,
    }


class OnlineUserOut(BaseModel):
    id: int
    username: str
    avatar_color: Optional[str] = None


@router.get("/users/online", response_model=list[OnlineUserOut])
def list_online_users(
    db: sqlite3.Connection = Depends(get_db),
    _user: sqlite3.Row = Depends(get_current_user),
):
    """Return users currently subscribed to SSE, ordered by id ascending.

    Source of truth: `broker.online_user_ids()` (in-memory set of user_ids
    with at least one open SSE queue). Frontend reconciles via 30s polling
    + SSE merge (user_online/user_offline events from this broker).
    """
    from backend.shared.sse import broker
    ids = sorted(broker.online_user_ids())
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = db.execute(
        f"SELECT id, username, avatar_color FROM users "
        f"WHERE id IN ({placeholders}) ORDER BY id ASC",
        tuple(ids),
    ).fetchall()
    return [
        {"id": r["id"], "username": r["username"], "avatar_color": r["avatar_color"]}
        for r in rows
    ]


from pydantic import BaseModel as _BaseModel, Field

from backend.users.deps import require_admin
from backend.users.models import UsersListResponse


class RotateInviteRequest(_BaseModel):
    # Strict alphabet + 8-32 char range. Without min/max an admin could
    # rotate to "" and brick registration; without a pattern an admin
    # could rotate to a value containing whitespace / control bytes that
    # later fail subtle string-equality checks.
    new_code: str = Field(
        min_length=8,
        max_length=32,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


@router.get("/admin/users", response_model=UsersListResponse)
def list_users(
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    rows = db.execute(
        "SELECT * FROM users ORDER BY id"
    ).fetchall()
    users = [_user_to_out(r) for r in rows]
    return {"users": users, "total": len(users)}


@router.post("/admin/users/{user_id}/promote", response_model=OkResponse)
def admin_promote(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    try:
        service.promote_admin(
            db, admin_user_id=admin["id"], target_user_id=user_id,
            trace_id=trace_id,
        )
    except service.UserNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.post("/admin/users/{user_id}/demote", response_model=OkResponse)
def admin_demote(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    try:
        service.demote_admin(
            db, admin_user_id=admin["id"], target_user_id=user_id,
            trace_id=trace_id,
        )
    except service.UserNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except service.LastAdminCannotBeRemoved as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/admin/users/{user_id}/disable", response_model=OkResponse)
def admin_disable(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    try:
        service.disable_user(
            db, admin_user_id=admin["id"], target_user_id=user_id,
            trace_id=trace_id,
        )
    except service.UserNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except service.LastAdminCannotBeRemoved as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/admin/users/{user_id}/enable", response_model=OkResponse)
def admin_enable(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    try:
        service.enable_user(
            db, admin_user_id=admin["id"], target_user_id=user_id,
            trace_id=trace_id,
        )
    except service.UserNotFound:
        raise HTTPException(
            status_code=404,
            detail={"error": "user_not_found", "message": f"User {user_id} not found"},
        )
    return {"ok": True}


@router.post("/admin/invite/rotate")
def admin_rotate_invite(
    payload: RotateInviteRequest,
    db: sqlite3.Connection = Depends(get_db),
    admin: sqlite3.Row = Depends(require_admin),
):
    trace_id = audit.gen_trace_id()
    new_code = service.rotate_invite_code(
        db, admin_user_id=admin["id"], new_code=payload.new_code,
        trace_id=trace_id,
    )
    return {"ok": True, "new_code": new_code}
