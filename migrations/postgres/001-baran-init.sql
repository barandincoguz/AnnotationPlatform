-- ============================================================
-- baran_* mirror DDL — Phase 4 generated artifact.
-- Source: SQLite project schema (22 in-scope tables).
-- Regenerate with: python -m scripts.regen_neon_ddl
-- Idempotent: every CREATE uses IF NOT EXISTS.
-- ============================================================

CREATE TABLE IF NOT EXISTS baran_documents_meta (
    document_id text PRIMARY KEY,
    file_path text NOT NULL,
    sayi bigint,
    tarih text,
    basvuru_tarihi text,
    vergi_donemi text,
    konu text,
    vergi_turu text,
    mukellefiyet_turu text,
    pdf_text text NOT NULL,
    html_text text,
    word_count bigint NOT NULL,
    sentence_count bigint NOT NULL,
    text_density double precision NOT NULL,
    estimated_difficulty text NOT NULL,
    topic_category text,
    created_at text NOT NULL,
    CHECK (estimated_difficulty IN ('Kolay','Orta','Zor'))
);

CREATE INDEX IF NOT EXISTS baran_idx_docs_sayi ON baran_documents_meta(sayi);

CREATE INDEX IF NOT EXISTS baran_idx_docs_konu ON baran_documents_meta(konu);

CREATE INDEX IF NOT EXISTS baran_idx_docs_tarih ON baran_documents_meta(tarih);

CREATE INDEX IF NOT EXISTS baran_idx_docs_topic ON baran_documents_meta(topic_category);

CREATE INDEX IF NOT EXISTS baran_idx_docs_difficulty ON baran_documents_meta(estimated_difficulty);

CREATE TABLE IF NOT EXISTS baran_system_events (
    id bigserial PRIMARY KEY,
    event_type text NOT NULL,
    severity text NOT NULL,
    message text,
    extra_json jsonb,
    created_at text NOT NULL,
    trace_id text,
    CHECK (severity IN ('info','warn','error'))
);

CREATE INDEX IF NOT EXISTS baran_idx_sys_trace ON baran_system_events(trace_id) WHERE trace_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS baran_idx_sys_type ON baran_system_events(event_type);

CREATE INDEX IF NOT EXISTS baran_idx_sys_severity_time ON baran_system_events(severity, created_at);

CREATE TABLE IF NOT EXISTS baran_users (
    id bigserial PRIMARY KEY,
    username text NOT NULL,
    email text,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'user',
    is_active bigint NOT NULL DEFAULT 1,
    has_passed_training bigint NOT NULL DEFAULT 0,
    has_seen_manual bigint NOT NULL DEFAULT 0,
    avatar_color text,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    CHECK (role IN ('user','admin'))
);

CREATE INDEX IF NOT EXISTS baran_idx_users_role ON baran_users(role);

CREATE INDEX IF NOT EXISTS baran_idx_users_active ON baran_users(is_active);

CREATE TABLE IF NOT EXISTS baran_annotation_references (
    id bigserial PRIMARY KEY,
    document_id text NOT NULL REFERENCES baran_documents_meta(document_id) ON DELETE CASCADE,
    seq bigint NOT NULL,
    kanun_no text,
    kanun_ad text,
    madde text,
    fikra text,
    bent text,
    source_text text NOT NULL
);

CREATE INDEX IF NOT EXISTS baran_idx_annref_kanun_madde ON baran_annotation_references(kanun_no, madde);

CREATE INDEX IF NOT EXISTS baran_idx_annref_kanun ON baran_annotation_references(kanun_no);

CREATE INDEX IF NOT EXISTS baran_idx_annref_doc ON baran_annotation_references(document_id);

CREATE TABLE IF NOT EXISTS baran_document_bkk_refs (
    id bigserial PRIMARY KEY,
    document_id text NOT NULL REFERENCES baran_documents_meta(document_id) ON DELETE CASCADE,
    seq bigint NOT NULL,
    turu text,
    kanun_kodu text,
    madde_no text
);

CREATE INDEX IF NOT EXISTS baran_idx_docbkk_doc ON baran_document_bkk_refs(document_id);

CREATE TABLE IF NOT EXISTS baran_document_kanun_refs (
    id bigserial PRIMARY KEY,
    document_id text NOT NULL REFERENCES baran_documents_meta(document_id) ON DELETE CASCADE,
    seq bigint NOT NULL,
    kanun_kodu text NOT NULL,
    kanun_maddesi text,
    kanun_maddesi_turu text
);

CREATE INDEX IF NOT EXISTS baran_idx_dockanun_doc ON baran_document_kanun_refs(document_id);

CREATE TABLE IF NOT EXISTS baran_activity_events (
    id bigserial PRIMARY KEY,
    user_id bigint REFERENCES baran_users(id) ON DELETE SET NULL,
    session_id bigint,
    event_type text NOT NULL,
    document_id text,
    duration_ms bigint,
    extra_json jsonb,
    created_at text NOT NULL
);

CREATE INDEX IF NOT EXISTS baran_idx_act_created_user_type ON baran_activity_events(created_at, user_id, event_type);

CREATE INDEX IF NOT EXISTS baran_idx_act_type_time ON baran_activity_events(event_type, created_at);

CREATE INDEX IF NOT EXISTS baran_idx_act_doc_time ON baran_activity_events(document_id, created_at);

CREATE INDEX IF NOT EXISTS baran_idx_act_user_time ON baran_activity_events(user_id, created_at);

CREATE TABLE IF NOT EXISTS baran_admin_audit_log (
    id bigserial PRIMARY KEY,
    admin_user_id bigint REFERENCES baran_users(id) ON DELETE SET NULL,
    action_type text NOT NULL,
    target_kind text,
    target_id text,
    metadata_json jsonb,
    created_at text NOT NULL,
    trace_id text,
    hash text,
    prev_hash text
);

CREATE INDEX IF NOT EXISTS baran_idx_audit_hash ON baran_admin_audit_log(hash) WHERE hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS baran_idx_audit_trace ON baran_admin_audit_log(trace_id) WHERE trace_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS baran_idx_audit_action ON baran_admin_audit_log(action_type);

CREATE INDEX IF NOT EXISTS baran_idx_audit_admin_time ON baran_admin_audit_log(admin_user_id, created_at);

CREATE TABLE IF NOT EXISTS baran_annotation_versions (
    id bigserial PRIMARY KEY,
    document_id text NOT NULL REFERENCES baran_documents_meta(document_id) ON DELETE CASCADE,
    user_id bigint REFERENCES baran_users(id) ON DELETE SET NULL,
    references_json jsonb NOT NULL,
    diff_from_previous text,
    is_diff_zero bigint NOT NULL DEFAULT 0,
    action text NOT NULL,
    created_at text NOT NULL
);

CREATE INDEX IF NOT EXISTS baran_idx_ver_created_user ON baran_annotation_versions(created_at, user_id);

CREATE INDEX IF NOT EXISTS baran_idx_ver_doc_user ON baran_annotation_versions(document_id, user_id);

CREATE INDEX IF NOT EXISTS baran_idx_ver_diff_zero ON baran_annotation_versions(is_diff_zero);

CREATE INDEX IF NOT EXISTS baran_idx_ver_user_time ON baran_annotation_versions(user_id, created_at);

CREATE INDEX IF NOT EXISTS baran_idx_ver_doc_time ON baran_annotation_versions(document_id, created_at);

CREATE TABLE IF NOT EXISTS baran_annotations (
    document_id text PRIMARY KEY REFERENCES baran_documents_meta(document_id) ON DELETE CASCADE,
    references_json jsonb NOT NULL DEFAULT '[]',
    is_completed bigint NOT NULL DEFAULT 0,
    last_editor_user_id bigint REFERENCES baran_users(id) ON DELETE SET NULL,
    completed_by_user_id bigint REFERENCES baran_users(id) ON DELETE SET NULL,
    edit_count bigint NOT NULL DEFAULT 0,
    unique_users_count bigint NOT NULL DEFAULT 0,
    created_at text NOT NULL,
    updated_at text NOT NULL
);

CREATE INDEX IF NOT EXISTS baran_idx_ann_editor ON baran_annotations(last_editor_user_id);

CREATE INDEX IF NOT EXISTS baran_idx_ann_completed ON baran_annotations(is_completed);

CREATE TABLE IF NOT EXISTS baran_badges_earned (
    user_id bigint NOT NULL REFERENCES baran_users(id) ON DELETE CASCADE,
    badge_id text NOT NULL,
    earned_at text NOT NULL,
    PRIMARY KEY (user_id, badge_id)
);

CREATE TABLE IF NOT EXISTS baran_behavioral_events (
    id bigserial PRIMARY KEY,
    user_id bigint REFERENCES baran_users(id) ON DELETE SET NULL,
    detector text NOT NULL,
    threshold_value double precision,
    actual_value double precision,
    context_json jsonb,
    created_at text NOT NULL
);

CREATE INDEX IF NOT EXISTS baran_idx_beh_detector ON baran_behavioral_events(detector);

CREATE INDEX IF NOT EXISTS baran_idx_beh_user_time ON baran_behavioral_events(user_id, created_at);

CREATE TABLE IF NOT EXISTS baran_document_locks (
    document_id text PRIMARY KEY REFERENCES baran_documents_meta(document_id) ON DELETE CASCADE,
    user_id bigint NOT NULL REFERENCES baran_users(id) ON DELETE CASCADE,
    acquired_at text NOT NULL,
    last_heartbeat text NOT NULL,
    expires_at text NOT NULL
);

CREATE INDEX IF NOT EXISTS baran_idx_lock_expires ON baran_document_locks(expires_at);

CREATE INDEX IF NOT EXISTS baran_idx_lock_user ON baran_document_locks(user_id);

CREATE TABLE IF NOT EXISTS baran_drafts (
    document_id text NOT NULL REFERENCES baran_documents_meta(document_id) ON DELETE CASCADE,
    user_id bigint NOT NULL REFERENCES baran_users(id) ON DELETE CASCADE,
    references_json jsonb NOT NULL DEFAULT '[]',
    updated_at text NOT NULL,
    PRIMARY KEY (document_id, user_id)
);

CREATE TABLE IF NOT EXISTS baran_gamification_ledger (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES baran_users(id) ON DELETE CASCADE,
    delta_xp bigint NOT NULL,
    reason text NOT NULL,
    related_doc_id text,
    created_at text NOT NULL
);

CREATE INDEX IF NOT EXISTS baran_idx_ledger_created_user ON baran_gamification_ledger(created_at, user_id);

CREATE INDEX IF NOT EXISTS baran_idx_ledger_user_time ON baran_gamification_ledger(user_id, created_at);

CREATE TABLE IF NOT EXISTS baran_gamification_state (
    user_id bigint PRIMARY KEY REFERENCES baran_users(id) ON DELETE CASCADE,
    total_xp bigint NOT NULL DEFAULT 0,
    current_streak_days bigint NOT NULL DEFAULT 0,
    longest_streak_days bigint NOT NULL DEFAULT 0,
    last_active_date text,
    today_save_count bigint NOT NULL DEFAULT 0,
    today_complete_count bigint NOT NULL DEFAULT 0,
    today_review_count bigint NOT NULL DEFAULT 0,
    today_skip_count bigint NOT NULL DEFAULT 0,
    updated_at text NOT NULL
);

CREATE TABLE IF NOT EXISTS baran_invite_codes (
    id bigserial PRIMARY KEY,
    code text NOT NULL,
    is_active bigint NOT NULL DEFAULT 1,
    created_by_admin_id bigint REFERENCES baran_users(id) ON DELETE SET NULL,
    rotated_at text,
    created_at text NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS baran_idx_invite_active ON baran_invite_codes(is_active) WHERE is_active=1;

CREATE TABLE IF NOT EXISTS baran_notifications (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES baran_users(id) ON DELETE CASCADE,
    kind text NOT NULL,
    title text NOT NULL,
    body text,
    data_json jsonb,
    is_read bigint NOT NULL DEFAULT 0,
    created_at text NOT NULL
);

CREATE INDEX IF NOT EXISTS baran_idx_notif_user_unread ON baran_notifications(user_id, is_read);

CREATE TABLE IF NOT EXISTS baran_site_settings (
    key text PRIMARY KEY,
    value text NOT NULL,
    description text,
    updated_at text NOT NULL,
    updated_by_user_id bigint REFERENCES baran_users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS baran_training_attempts (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES baran_users(id) ON DELETE CASCADE,
    attempt_number bigint NOT NULL,
    quiz_score bigint NOT NULL,
    quiz_total bigint NOT NULL,
    annotation_pass_count bigint NOT NULL,
    annotation_total bigint NOT NULL,
    annotation_details_json jsonb,
    passed bigint NOT NULL,
    started_at text NOT NULL,
    finished_at text
);

CREATE INDEX IF NOT EXISTS baran_idx_train_user ON baran_training_attempts(user_id);

CREATE TABLE IF NOT EXISTS baran_training_gold_doc_overrides (
    gold_id text PRIMARY KEY,
    is_deleted bigint NOT NULL DEFAULT 0,
    content text,
    expected_concepts text,
    min_concept_count bigint,
    source text NOT NULL,
    created_by_admin_id bigint REFERENCES baran_users(id) ON DELETE SET NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    CHECK (source IN ('override','custom'))
);

CREATE TABLE IF NOT EXISTS baran_training_quiz_overrides (
    question_id text PRIMARY KEY,
    is_deleted bigint NOT NULL DEFAULT 0,
    text text,
    choices_json jsonb,
    correct_choice_idx bigint,
    source text NOT NULL,
    created_by_admin_id bigint REFERENCES baran_users(id) ON DELETE SET NULL,
    created_at text NOT NULL,
    updated_at text NOT NULL,
    CHECK (source IN ('override','custom'))
);

CREATE INDEX IF NOT EXISTS baran_idx_quiz_overrides_active ON baran_training_quiz_overrides(question_id) WHERE is_deleted=0;

COMMIT;
