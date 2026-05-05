"""Initial schema: 19 tables across 4 domains + default site_settings seed."""
import json
import sqlite3
from datetime import datetime, timezone


SCHEMA_SQL = """
-- ============================================================
-- A. CORE — data of record (8 tables)
-- ============================================================

CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    email           TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    has_passed_training INTEGER NOT NULL DEFAULT 0,
    has_seen_manual INTEGER NOT NULL DEFAULT 0,
    avatar_color    TEXT,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_users_active ON users(is_active);
CREATE INDEX idx_users_role ON users(role);

CREATE TABLE invite_codes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_by_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    rotated_at      TIMESTAMP,
    created_at      TIMESTAMP NOT NULL
);
CREATE UNIQUE INDEX idx_invite_active ON invite_codes(is_active) WHERE is_active=1;

CREATE TABLE site_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    description     TEXT,
    updated_at      TIMESTAMP NOT NULL,
    updated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE documents_meta (
    document_id     TEXT PRIMARY KEY,
    file_path       TEXT NOT NULL,
    word_count      INTEGER NOT NULL,
    sentence_count  INTEGER NOT NULL,
    text_density    REAL NOT NULL,
    estimated_difficulty TEXT NOT NULL CHECK(estimated_difficulty IN ('Kolay','Orta','Zor')),
    ozelge_no       TEXT,
    topic_category  TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_docs_difficulty ON documents_meta(estimated_difficulty);
CREATE INDEX idx_docs_topic ON documents_meta(topic_category);
CREATE INDEX idx_docs_ozelge ON documents_meta(ozelge_no);

CREATE TABLE annotations (
    document_id     TEXT PRIMARY KEY REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    question_1      TEXT,
    question_2      TEXT,
    question_3      TEXT,
    is_completed    INTEGER NOT NULL DEFAULT 0,
    last_editor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    completed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    edit_count      INTEGER NOT NULL DEFAULT 0,
    unique_users_count INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_ann_completed ON annotations(is_completed);
CREATE INDEX idx_ann_editor ON annotations(last_editor_user_id);

CREATE TABLE annotation_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     TEXT NOT NULL REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    question_1      TEXT,
    question_2      TEXT,
    question_3      TEXT,
    diff_from_previous TEXT,
    is_diff_zero    INTEGER NOT NULL DEFAULT 0,
    action          TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_ver_doc_time ON annotation_versions(document_id, created_at DESC);
CREATE INDEX idx_ver_user_time ON annotation_versions(user_id, created_at DESC);
CREATE INDEX idx_ver_diff_zero ON annotation_versions(is_diff_zero);

CREATE TABLE drafts (
    document_id     TEXT NOT NULL REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_1      TEXT,
    question_2      TEXT,
    question_3      TEXT,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (document_id, user_id)
);

CREATE TABLE document_locks (
    document_id     TEXT PRIMARY KEY REFERENCES documents_meta(document_id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    acquired_at     TIMESTAMP NOT NULL,
    last_heartbeat  TIMESTAMP NOT NULL,
    expires_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_lock_user ON document_locks(user_id);
CREATE INDEX idx_lock_expires ON document_locks(expires_at);

-- ============================================================
-- B. EVENT LOGS — append-only (5 tables)
-- ============================================================

CREATE TABLE user_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token   TEXT NOT NULL,
    ip_hash         TEXT,
    user_agent      TEXT,
    started_at      TIMESTAMP NOT NULL,
    ended_at        TIMESTAMP,
    last_activity_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_session_user_active ON user_sessions(user_id, ended_at);
CREATE INDEX idx_session_token ON user_sessions(session_token);

CREATE TABLE activity_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    session_id      INTEGER REFERENCES user_sessions(id) ON DELETE SET NULL,
    event_type      TEXT NOT NULL,
    document_id     TEXT,
    duration_ms     INTEGER,
    extra_json      TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_act_user_time ON activity_events(user_id, created_at DESC);
CREATE INDEX idx_act_doc_time ON activity_events(document_id, created_at DESC);
CREATE INDEX idx_act_type_time ON activity_events(event_type, created_at DESC);

CREATE TABLE behavioral_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    detector        TEXT NOT NULL,
    threshold_value REAL,
    actual_value    REAL,
    context_json    TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_beh_user_time ON behavioral_events(user_id, created_at DESC);
CREATE INDEX idx_beh_detector ON behavioral_events(detector);

CREATE TABLE admin_audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
    action_type     TEXT NOT NULL,
    target_kind     TEXT,
    target_id       TEXT,
    metadata_json   TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_audit_admin_time ON admin_audit_log(admin_user_id, created_at DESC);
CREATE INDEX idx_audit_action ON admin_audit_log(action_type);

CREATE TABLE system_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK(severity IN ('info','warn','error')),
    message         TEXT,
    extra_json      TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_sys_severity_time ON system_events(severity, created_at DESC);
CREATE INDEX idx_sys_type ON system_events(event_type);

-- ============================================================
-- C. AUXILIARY (5 tables)
-- ============================================================

CREATE TABLE gamification_state (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    total_xp        INTEGER NOT NULL DEFAULT 0,
    current_streak_days INTEGER NOT NULL DEFAULT 0,
    longest_streak_days INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT,
    today_save_count INTEGER NOT NULL DEFAULT 0,
    today_complete_count INTEGER NOT NULL DEFAULT 0,
    today_review_count INTEGER NOT NULL DEFAULT 0,
    today_skip_count INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMP NOT NULL
);

CREATE TABLE gamification_ledger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    delta_xp        INTEGER NOT NULL,
    reason          TEXT NOT NULL,
    related_doc_id  TEXT,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_ledger_user_time ON gamification_ledger(user_id, created_at DESC);

CREATE TABLE badges_earned (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    badge_id        TEXT NOT NULL,
    earned_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, badge_id)
);

CREATE TABLE training_attempts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    attempt_number  INTEGER NOT NULL,
    quiz_score      INTEGER NOT NULL,
    quiz_total      INTEGER NOT NULL,
    annotation_pass_count INTEGER NOT NULL,
    annotation_total INTEGER NOT NULL,
    annotation_details_json TEXT,
    passed          INTEGER NOT NULL,
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP NOT NULL
);
CREATE INDEX idx_train_user ON training_attempts(user_id);

CREATE TABLE notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,
    data_json       TEXT,
    is_read         INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_notif_user_unread ON notifications(user_id, is_read);

-- ============================================================
-- D. HYBRID OVERRIDE (Q5 resolution)
-- ============================================================

CREATE TABLE training_gold_doc_overrides (
    gold_id         TEXT PRIMARY KEY,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    content         TEXT,
    expected_concepts TEXT,
    min_concept_count INTEGER,
    source          TEXT NOT NULL CHECK(source IN ('override','custom')),
    created_by_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);
"""


DEFAULT_SETTINGS: dict[str, tuple[object, str]] = {
    # Speed warning
    "speed_warning.window_seconds": (300, "Hız uyarısı için zaman penceresi (saniye)"),
    "speed_warning.max_saves_in_window": (5, "Pencerede izin verilen max save sayısı"),
    "speed_warning.min_seconds_per_doc": (30, "Bir dokümanda minimum kalma süresi"),
    "speed_warning.min_words_for_min_seconds": (100, "Yukarıdaki kuralın geçerli olduğu min kelime sayısı"),
    # Char limit
    "char_limit.warn_threshold": (300, "Soru başına turuncu uyarı eşiği"),
    "char_limit.alert_threshold": (600, "Soru başına kırmızı uyarı eşiği"),
    # Lock
    "lock.expires_seconds": (300, "Doküman kilidi idle timeout (saniye)"),
    "lock.heartbeat_interval_seconds": (30, "Frontend heartbeat sıklığı"),
    # Backup
    "backup.interval_seconds": (600, "GitHub backup sıklığı (10dk)"),
    # Training
    "training.quiz_pass_threshold": (4, "5 sorudan en az kaç doğru gerekli"),
    "training.annotation_pass_threshold": (2, "3 gold doc'tan en az kaç pass gerekli"),
    "training.max_attempts": (3, "Toplam deneme hakkı"),
    # Gamification
    "gamification.daily_target_docs": (20, "Günlük hedef doc sayısı"),
    "gamification.xp_save": (1, "Sakla başına XP"),
    "gamification.xp_complete": (5, "Tamamlandı işaretle başına XP"),
    "gamification.xp_review": (2, "Review (mevcut annotation düzenle) başına XP"),
    "gamification.xp_review_kept": (3, "Review'in sonraki kullanıcı tarafından korunması bonusu"),
    "gamification.xp_training_pass": (50, "Training pass one-time bonus"),
    "gamification.good_reviewer.min_reviews": (20, "Good Reviewer rozeti min review sayısı"),
    "gamification.good_reviewer.min_kept": (15, "Good Reviewer min korunmuş review sayısı"),
}


def _seed_default_settings(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for key, (value, description) in DEFAULT_SETTINGS.items():
        conn.execute(
            """
            INSERT INTO site_settings(key, value, description, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (key, json.dumps(value), description, now),
        )


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    _seed_default_settings(conn)
