"""Auth + user routes."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend import config
from backend.users import service
from backend.users.deps import (
    get_db, get_current_user, get_request_ip
)
from backend.users.models import (
    RegisterRequest, LoginRequest, UserOut, OkResponse,
)

router = APIRouter(prefix="/api", tags=["users"])


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
        secure=False,  # set true behind HTTPS in prod via env
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
