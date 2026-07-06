from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend import config
from backend.shared.db import connect


TR_TZ = ZoneInfo("Europe/Istanbul")


def _ts_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _insert_doc(conn, document_id: str) -> None:
    conn.execute(
        """
        INSERT INTO documents_meta(
            document_id, file_path, pdf_text, word_count, sentence_count,
            text_density, estimated_difficulty, created_at
        ) VALUES (?, ?, ?, 1, 1, 1.0, 'Kolay', ?)
        """,
        (document_id, f"{document_id}.json", "text", _ts_days_ago(0)),
    )


def _insert_user(conn, username: str, *, passed_training: bool = True) -> int:
    now = _ts_days_ago(0)
    cur = conn.execute(
        """
        INSERT INTO users(
            username, email, password_hash, role, is_active,
            has_passed_training, has_seen_manual, avatar_color,
            created_at, updated_at
        ) VALUES (?, ?, 'hash', 'user', 1, ?, ?, '#64748b', ?, ?)
        """,
        (
            username,
            f"{username}@example.com",
            1 if passed_training else 0,
            1 if passed_training else 0,
            now,
            now,
        ),
    )
    user_id = int(cur.lastrowid)
    conn.execute(
        """
        INSERT INTO gamification_state(
            user_id, total_xp, current_streak_days, longest_streak_days,
            last_active_date, today_save_count, today_complete_count,
            today_review_count, today_skip_count, updated_at
        ) VALUES (?, 0, 0, 0, NULL, 0, 0, 0, 0, ?)
        """,
        (user_id, now),
    )
    return user_id


def _insert_passed_user(conn, username: str) -> int:
    return _insert_user(conn, username, passed_training=True)


def _seed_statistics_rows(conn, alice_id: int, bob_id: int) -> None:
    for doc_id in ("doc_today", "doc_recent", "doc_old", "doc_bob"):
        _insert_doc(conn, doc_id)

    now = _ts_days_ago(0)
    recent = _ts_days_ago(3)
    old = _ts_days_ago(40)

    conn.execute(
        """
        UPDATE gamification_state
           SET total_xp=25, current_streak_days=4, last_active_date=?
         WHERE user_id=?
        """,
        (datetime.now(TR_TZ).date().isoformat(), alice_id),
    )
    conn.execute(
        "INSERT INTO badges_earned(user_id, badge_id, earned_at) VALUES (?, 'first_annotation', ?)",
        (alice_id, now),
    )

    activity_rows = [
        (alice_id, "annotation_save", "doc_today", now),
        (alice_id, "annotation_skip", "doc_today", now),
        (alice_id, "complete_mark", "doc_recent", recent),
        (alice_id, "uncomplete", "doc_old", old),
        (bob_id, "annotation_save", "doc_bob", now),
    ]
    for user_id, event_type, document_id, created_at in activity_rows:
        conn.execute(
            """
            INSERT INTO activity_events(user_id, event_type, document_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, event_type, document_id, created_at),
        )

    version_rows = [
        (alice_id, "doc_today", "create", 0, now),
        (alice_id, "doc_recent", "edit", 1, recent),
        (alice_id, "doc_recent", "complete_mark", 1, recent),
        (alice_id, "doc_old", "uncomplete", 1, old),
        (bob_id, "doc_bob", "create", 0, now),
    ]
    for user_id, document_id, action, is_diff_zero, created_at in version_rows:
        conn.execute(
            """
            INSERT INTO annotation_versions(
                document_id, user_id, references_json, diff_from_previous,
                is_diff_zero, action, created_at
            ) VALUES (?, ?, '[]', '{"added":[],"removed":[]}', ?, ?, ?)
            """,
            (document_id, user_id, is_diff_zero, action, created_at),
        )

    conn.execute(
        """
        INSERT INTO annotations(
            document_id, references_json, is_completed, last_editor_user_id,
            completed_by_user_id, edit_count, unique_users_count,
            created_at, updated_at
        ) VALUES ('doc_recent', '[]', 1, ?, ?, 2, 1, ?, ?)
        """,
        (alice_id, alice_id, recent, recent),
    )
    conn.execute(
        """
        INSERT INTO annotations(
            document_id, references_json, is_completed, last_editor_user_id,
            completed_by_user_id, edit_count, unique_users_count,
            created_at, updated_at
        ) VALUES ('doc_old', '[]', 1, ?, ?, 1, 1, ?, ?)
        """,
        (alice_id, alice_id, old, old),
    )

    ledger_rows = [(alice_id, 10, now), (alice_id, 5, recent), (alice_id, 2, old)]
    for user_id, delta_xp, created_at in ledger_rows:
        conn.execute(
            """
            INSERT INTO gamification_ledger(user_id, delta_xp, reason, related_doc_id, created_at)
            VALUES (?, ?, 'test', NULL, ?)
            """,
            (user_id, delta_xp, created_at),
        )


def test_statistics_requires_auth(client):
    r = client.get("/api/statistics/users")
    assert r.status_code == 401


def test_statistics_requires_passed_training(client, seen_manual_user):
    seen_manual_user("prestats", "STATS-PRE")
    r = client.get("/api/statistics/users")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "training_not_passed"


def test_statistics_allows_non_admin_and_omits_sensitive_user_fields(passed_user):
    r = passed_user["client"].get("/api/statistics/users")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"generated_at", "summary", "users"}
    user = body["users"][0]["user"]
    assert user["username"] == "alice"
    assert "email" not in user
    assert "password_hash" not in user


def test_statistics_includes_zero_activity_passed_users(passed_user):
    conn = connect(config.DB_PATH)
    try:
        zero_id = _insert_passed_user(conn, "zero_stats")
    finally:
        conn.close()

    r = passed_user["client"].get("/api/statistics/users")
    assert r.status_code == 200, r.text
    rows = {u["user"]["username"]: u for u in r.json()["users"]}
    zero = rows["zero_stats"]
    assert zero["user"]["id"] == zero_id
    assert zero["xp_total"] == 0
    assert zero["badges_count"] == 0
    assert zero["streak_current"] == 0
    assert zero["last_active_date"] is None
    assert zero["metrics"]["all_time"]["distinct_documents"] == 0
    assert zero["metrics"]["all_time"]["save_events"] == 0
    assert zero["metrics"]["all_time"]["xp_delta"] == 0


def test_statistics_includes_accounts_that_have_not_passed_training(passed_user):
    conn = connect(config.DB_PATH)
    try:
        newbie_id = _insert_user(conn, "newbie_stats", passed_training=False)
    finally:
        conn.close()

    r = passed_user["client"].get("/api/statistics/users")
    assert r.status_code == 200, r.text
    rows = {u["user"]["username"]: u for u in r.json()["users"]}
    newbie = rows["newbie_stats"]
    assert newbie["user"]["id"] == newbie_id
    assert newbie["metrics"]["all_time"]["distinct_documents"] == 0
    assert newbie["metrics"]["all_time"]["version_events"] == 0


def test_statistics_aggregates_per_user_and_summary_across_periods(passed_user):
    alice_id = passed_user["user"]["id"]
    conn = connect(config.DB_PATH)
    try:
        bob_id = _insert_passed_user(conn, "bob_stats")
        _seed_statistics_rows(conn, alice_id, bob_id)
    finally:
        conn.close()

    r = passed_user["client"].get("/api/statistics/users")
    assert r.status_code == 200, r.text
    body = r.json()
    users = {u["user"]["username"]: u for u in body["users"]}

    alice = users["alice"]
    assert alice["xp_total"] == 25
    assert alice["badges_count"] == 1
    assert alice["streak_current"] == 4

    all_time = alice["metrics"]["all_time"]
    assert all_time == {
        "distinct_documents": 3,
        "save_events": 1,
        "complete_events": 1,
        "uncomplete_events": 1,
        "skip_events": 1,
        "version_events": 4,
        "create_versions": 1,
        "edit_versions": 1,
        "complete_mark_versions": 1,
        "zero_diff_versions": 3,
        "final_completed_documents": 2,
        "xp_delta": 17,
    }

    today = alice["metrics"]["today"]
    assert today["distinct_documents"] == 1
    assert today["save_events"] == 1
    assert today["skip_events"] == 1
    assert today["complete_events"] == 0
    assert today["version_events"] == 1
    assert today["final_completed_documents"] == 0
    assert today["xp_delta"] == 10

    last_7 = alice["metrics"]["last_7_days"]
    assert last_7["distinct_documents"] == 2
    assert last_7["complete_events"] == 1
    assert last_7["uncomplete_events"] == 0
    assert last_7["version_events"] == 3
    assert last_7["final_completed_documents"] == 1
    assert last_7["xp_delta"] == 15

    summary_all_time = body["summary"]["all_time"]
    assert summary_all_time["distinct_documents"] == 4
    assert summary_all_time["save_events"] == 2
    assert summary_all_time["version_events"] == 5
    assert summary_all_time["final_completed_documents"] == 2
    assert summary_all_time["xp_delta"] == 17
