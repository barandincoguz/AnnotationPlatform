"""Audit flow must not distort speed_warning or blame users for model quotes."""
import json

LONG_MODEL_QUOTE = "M" + "odel alintisi " * 40          # > 300 chars
LONG_HUMAN_QUOTE = "K" + "endi alintim " * 40           # > 300 chars
DOC_TEXT = "kisa dokuman metni"


def test_char_limit_warning_exempts_quotes_that_match_model_output():
    from backend.behavioral.service import detect_char_limit_warning

    references = [{"kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
                   "fikra": None, "bent": None, "source_text": LONG_MODEL_QUOTE}]
    # No exemption → warns.
    assert detect_char_limit_warning(_FakeDb(), references=references) is not None
    # Exempted → silent.
    assert detect_char_limit_warning(
        _FakeDb(), references=references, exempt_quotes=(LONG_MODEL_QUOTE,)
    ) is None


def test_char_limit_warning_still_fires_for_the_users_own_long_quote():
    from backend.behavioral.service import detect_char_limit_warning

    references = [{"kanun_no": "213", "kanun_ad": None, "madde": "114",
                   "fikra": None, "bent": None, "source_text": LONG_HUMAN_QUOTE}]
    verdict = detect_char_limit_warning(
        _FakeDb(), references=references, exempt_quotes=(LONG_MODEL_QUOTE,)
    )
    assert verdict is not None
    assert verdict["fields"][0]["field"] == "source_text"


def test_exemption_tolerates_whitespace_and_case_differences():
    from backend.behavioral.service import detect_char_limit_warning

    stored = LONG_MODEL_QUOTE.replace(" ", "\n").upper()
    references = [{"kanun_no": "213", "kanun_ad": None, "madde": "114",
                   "fikra": None, "bent": None, "source_text": stored}]
    assert detect_char_limit_warning(
        _FakeDb(), references=references, exempt_quotes=(LONG_MODEL_QUOTE,)
    ) is None


def test_pre_audit_calls_do_not_change_the_speed_warning_save_count(
    passed_user, ingest_doc
):
    from backend import config
    from backend.shared.db import connect

    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)

    def _save_count():
        conn = connect(config.DB_PATH)
        try:
            return conn.execute(
                "SELECT COUNT(*) AS c FROM activity_events"
                " WHERE event_type='annotation_save'"
            ).fetchone()["c"]
        finally:
            conn.close()

    before = _save_count()
    for _ in range(10):
        r = c.post("/api/annotations/d1/pre-audit", json={"references": []})
        assert r.status_code == 200
    assert _save_count() == before


def test_accepting_a_suggestion_via_draft_does_not_count_as_a_save(
    passed_user, ingest_doc
):
    from backend import config
    from backend.shared.db import connect

    c = passed_user["client"]
    ingest_doc("d1", pdfText=DOC_TEXT)
    reference = {"kanun_no": "213", "kanun_ad": "Vergi Usul Kanunu", "madde": "114",
                 "fikra": None, "bent": None, "source_text": "x"}
    for _ in range(8):
        assert c.put("/api/drafts/d1", json={"references": [reference]}).status_code == 200
    conn = connect(config.DB_PATH)
    try:
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM activity_events WHERE event_type='annotation_save'"
        ).fetchone()["c"] == 0
    finally:
        conn.close()


class _FakeDb:
    """char_limit thresholds come from settings; defaults apply when unset."""

    def execute(self, *_args, **_kwargs):
        class _Cursor:
            def fetchone(self):
                return None

            def fetchall(self):
                return []

        return _Cursor()
