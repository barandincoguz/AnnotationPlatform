"""B3: Admin quiz/gold-doc upsert payload validation (Pydantic model_validator guards)."""


# ── Quiz ────────────────────────────────────────────────────────────────────

def test_quiz_upsert_rejects_out_of_range_correct_idx(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "x", "choices": ["A", "B"], "correct_choice_idx": 5},
    )
    assert resp.status_code == 422


def test_quiz_upsert_rejects_single_choice(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "x", "choices": ["A"], "correct_choice_idx": 0},
    )
    assert resp.status_code == 422


def test_quiz_upsert_rejects_empty_text(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "", "choices": ["A", "B"], "correct_choice_idx": 0},
    )
    assert resp.status_code == 422


def test_quiz_upsert_rejects_empty_choice_string(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "Valid?", "choices": ["A", ""], "correct_choice_idx": 0},
    )
    assert resp.status_code == 422


def test_quiz_upsert_rejects_whitespace_only_choice(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "Valid?", "choices": ["A", "   "], "correct_choice_idx": 0},
    )
    assert resp.status_code == 422


def test_quiz_upsert_rejects_too_many_choices(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/quiz/q01",
        json={
            "text": "Valid?",
            "choices": ["A", "B", "C", "D", "E", "F", "G", "H", "I"],  # 9 choices
            "correct_choice_idx": 0,
        },
    )
    assert resp.status_code == 422


def test_quiz_upsert_accepts_valid_payload(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/quiz/q01",
        json={
            "text": "Hangi kanun?",
            "choices": ["A", "B", "C", "D"],
            "correct_choice_idx": 2,
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_quiz_upsert_accepts_two_choices(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/quiz/q01",
        json={"text": "Evet mi hayır mı?", "choices": ["Evet", "Hayır"], "correct_choice_idx": 1},
    )
    assert resp.status_code == 200


def test_quiz_upsert_accepts_eight_choices(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/quiz/q01",
        json={
            "text": "Hangisi?",
            "choices": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "correct_choice_idx": 7,
        },
    )
    assert resp.status_code == 200


# ── Gold Doc ─────────────────────────────────────────────────────────────────

def test_gold_doc_upsert_rejects_min_gt_expected_count(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/gold-docs/sample_kvk_5",
        json={
            "content": "Bazı içerik",
            "expected_concepts": [{"kanun_no": "5520"}, {"kanun_no": "193"}],
            "min_concept_count": 5,
        },
    )
    assert resp.status_code == 422


def test_gold_doc_upsert_rejects_empty_expected_concepts(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/gold-docs/sample_kvk_5",
        json={
            "content": "Bazı içerik",
            "expected_concepts": [],
            "min_concept_count": 1,
        },
    )
    assert resp.status_code == 422


def test_gold_doc_upsert_rejects_zero_min_concept_count(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/gold-docs/sample_kvk_5",
        json={
            "content": "Bazı içerik",
            "expected_concepts": [{"kanun_no": "5520"}],
            "min_concept_count": 0,
        },
    )
    assert resp.status_code == 422


def test_gold_doc_upsert_rejects_empty_content(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/gold-docs/sample_kvk_5",
        json={
            "content": "",
            "expected_concepts": [{"kanun_no": "5520"}],
            "min_concept_count": 1,
        },
    )
    assert resp.status_code == 422


def test_gold_doc_upsert_accepts_valid_payload(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/gold-docs/sample_kvk_5",
        json={
            "content": "Bu bir özelge metnidir.",
            "expected_concepts": [
                {"kanun_no": "5520", "madde": "5"},
                {"kanun_no": "193", "madde": "37"},
            ],
            "min_concept_count": 1,
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_gold_doc_upsert_accepts_min_equal_to_expected_count(client, bootstrap_admin):
    bootstrap_admin()
    resp = client.put(
        "/api/admin/training/gold-docs/sample_kvk_5",
        json={
            "content": "Metni",
            "expected_concepts": [{"kanun_no": "5520"}, {"kanun_no": "193"}],
            "min_concept_count": 2,
        },
    )
    assert resp.status_code == 200
