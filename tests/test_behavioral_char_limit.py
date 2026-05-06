"""Unit tests for behavioral.service.detect_char_limit_warning.

Returns None / warn / alert based on per-reference field lengths.
"""
import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared import settings as S
from backend.behavioral import service as behavioral


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _ref(kanun_ad="Kurumlar Vergisi Kanunu", source_text="kısa atıf", **overrides):
    base = {
        "kanun_no": "5520",
        "kanun_ad": kanun_ad,
        "madde": "5",
        "fikra": "1",
        "bent": "a",
        "source_text": source_text,
    }
    base.update(overrides)
    return base


def test_all_short_returns_none(db):
    """No field exceeds either threshold → None."""
    refs = [_ref(), _ref(kanun_ad="Gelir Vergisi", source_text="atıf metni")]
    assert behavioral.detect_char_limit_warning(db, references=refs) is None


def test_warn_threshold_hit_only(db):
    """A single source_text crosses warn (300) but not alert (600)."""
    refs = [_ref(source_text="x" * 301)]
    verdict = behavioral.detect_char_limit_warning(db, references=refs)
    assert verdict is not None
    assert verdict["level"] == "warn"
    assert verdict["warn_threshold"] == 300
    assert verdict["alert_threshold"] == 600
    assert len(verdict["fields"]) == 1
    f = verdict["fields"][0]
    assert f["ref_index"] == 0
    assert f["field"] == "source_text"
    assert f["length"] == 301
    assert f["level"] == "warn"


def test_alert_threshold_dominates(db):
    """If any field crosses alert, verdict.level=alert even when others only warn."""
    refs = [
        _ref(source_text="x" * 350),    # warn
        _ref(source_text="y" * 700),    # alert
    ]
    verdict = behavioral.detect_char_limit_warning(db, references=refs)
    assert verdict["level"] == "alert"
    # Both offending fields are reported
    assert len(verdict["fields"]) == 2
    levels = sorted(f["level"] for f in verdict["fields"])
    assert levels == ["alert", "warn"]


def test_kanun_ad_field_is_checked(db):
    """kanun_ad over warn threshold also triggers."""
    refs = [_ref(kanun_ad="Y" * 305, source_text="kısa")]
    verdict = behavioral.detect_char_limit_warning(db, references=refs)
    assert verdict["level"] == "warn"
    assert verdict["fields"][0]["field"] == "kanun_ad"


def test_other_fields_not_checked(db):
    """kanun_no/madde/fikra/bent are not checked even if long (they're short by domain)."""
    refs = [_ref(kanun_no="x" * 1000, madde="y" * 1000)]
    assert behavioral.detect_char_limit_warning(db, references=refs) is None


def test_empty_references_returns_none(db):
    """0 refs → no warning (a doc may have no legal references)."""
    assert behavioral.detect_char_limit_warning(db, references=[]) is None


def test_uses_settings_overrides(db):
    """Admin tunes warn=50, alert=100 → very short text now triggers."""
    S.set_value(db, "char_limit.warn_threshold", 50, updated_by_user_id=None)
    S.set_value(db, "char_limit.alert_threshold", 100, updated_by_user_id=None)
    refs = [_ref(source_text="x" * 60)]
    verdict = behavioral.detect_char_limit_warning(db, references=refs)
    assert verdict["level"] == "warn"
    assert verdict["warn_threshold"] == 50
    assert verdict["alert_threshold"] == 100


def test_threshold_boundary_not_inclusive(db):
    """Length == threshold is NOT a hit; length > threshold is. (Spec ambiguous; pick strict >.)"""
    refs = [_ref(source_text="x" * 300)]   # exactly == warn → no hit
    assert behavioral.detect_char_limit_warning(db, references=refs) is None
    refs = [_ref(source_text="x" * 301)]
    assert behavioral.detect_char_limit_warning(db, references=refs)["level"] == "warn"
