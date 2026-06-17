"""Badge definitions + check_badges detector.

`BADGE_DEFS` maps badge_id → {name, description}.
`check_badges(db, user_id)` returns the list of newly-unlocked badge IDs
(already-earned ones excluded). The orchestrator handles inserting the
badges_earned rows + creating notifications + publishing SSE.
"""
import sqlite3

from backend.shared import settings as S


BADGE_DEFS: dict[str, dict[str, str]] = {
    "first_annotation": {
        "name": "İlk Anotasyon",
        "description": "İlk kayıt başarıyla yapıldı.",
        "criterion": "İlk anotasyon kaydını yap.",
    },
    "annotations_10": {
        "name": "10 Anotasyon",
        "description": "10 kayıt biriktirdin.",
        "criterion": "10 anotasyon kaydı biriktir.",
    },
    "annotations_100": {
        "name": "100 Anotasyon",
        "description": "100 kayıt — istikrarlı çalışıyorsun.",
        "criterion": "100 anotasyon kaydı biriktir.",
    },
    "annotations_1000": {
        "name": "1000 Anotasyon",
        "description": "Bin kayıt: ekibin omurgası oldun.",
        "criterion": "1000 anotasyon kaydı biriktir.",
    },
    "first_completion": {
        "name": "İlk Tamamlama",
        "description": "İlk dokümanı tamamlandı olarak işaretledin.",
        "criterion": "İlk dokümanı tamamlandı olarak işaretle.",
    },
    "marathoner": {
        "name": "Maratoncu",
        "description": "7 gün üst üste çalıştın.",
        "criterion": "7 gün üst üste çalış.",
    },
    "good_reviewer": {
        "name": "Güvenilir İncelemeci",
        "description": "Yaptığın incelemelerin çoğu sonraki kullanıcılar tarafından korundu.",
        "criterion": "İncelemelerinin çoğunluğu korunsun (en az 20 inceleme, 15 korunan).",
    },
}


def _save_total(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS c FROM gamification_ledger "
        "WHERE user_id=? AND reason IN ('save','review')",
        (user_id,),
    ).fetchone()
    return row["c"]


def _complete_total(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS c FROM gamification_ledger "
        "WHERE user_id=? AND reason='complete'",
        (user_id,),
    ).fetchone()
    return row["c"]


def _review_total(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS c FROM gamification_ledger "
        "WHERE user_id=? AND reason='review'",
        (user_id,),
    ).fetchone()
    return row["c"]


def _review_kept_total(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS c FROM gamification_ledger "
        "WHERE user_id=? AND reason='review_kept'",
        (user_id,),
    ).fetchone()
    return row["c"]


def _current_streak(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT current_streak_days FROM gamification_state WHERE user_id=?",
        (user_id,),
    ).fetchone()
    return row["current_streak_days"] if row else 0


def _already_earned(db: sqlite3.Connection, user_id: int) -> set[str]:
    rows = db.execute(
        "SELECT badge_id FROM badges_earned WHERE user_id=?", (user_id,)
    ).fetchall()
    return {r["badge_id"] for r in rows}


def check_badges(db: sqlite3.Connection, *, user_id: int) -> list[str]:
    """Return the list of badge_ids the user newly qualifies for, excluding
    those already in badges_earned. Order is stable per insertion."""
    saves = _save_total(db, user_id)
    completes = _complete_total(db, user_id)
    streak = _current_streak(db, user_id)
    reviews = _review_total(db, user_id)
    kept = _review_kept_total(db, user_id)
    min_reviews = S.get_int(db, "gamification.good_reviewer.min_reviews", default=20)
    min_kept = S.get_int(db, "gamification.good_reviewer.min_kept", default=15)

    candidates: list[str] = []
    if saves >= 1:
        candidates.append("first_annotation")
    if saves >= 10:
        candidates.append("annotations_10")
    if saves >= 100:
        candidates.append("annotations_100")
    if saves >= 1000:
        candidates.append("annotations_1000")
    if completes >= 1:
        candidates.append("first_completion")
    if streak >= 7:
        candidates.append("marathoner")
    if reviews >= min_reviews and kept >= min_kept:
        candidates.append("good_reviewer")

    earned = _already_earned(db, user_id)
    return [b for b in candidates if b not in earned]
