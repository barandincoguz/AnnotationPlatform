import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.shared import settings as S


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def test_get_int_returns_seeded_default(db):
    assert S.get_int(db, "speed_warning.window_seconds") == 300


def test_get_int_missing_uses_default(db):
    assert S.get_int(db, "no.such.key", default=42) == 42


def test_get_int_missing_no_default_raises(db):
    with pytest.raises(KeyError):
        S.get_int(db, "no.such.key")


def test_set_persists_value(db):
    S.set_value(db, "test.key", 123, updated_by_user_id=None)
    assert S.get_int(db, "test.key") == 123


def test_set_overwrites_existing(db):
    S.set_value(db, "speed_warning.window_seconds", 600, None)
    assert S.get_int(db, "speed_warning.window_seconds") == 600


def test_get_dict_returns_dict(db):
    S.set_value(db, "test.dict", {"a": 1, "b": [2, 3]}, None)
    assert S.get_dict(db, "test.dict") == {"a": 1, "b": [2, 3]}


def test_get_str(db):
    S.set_value(db, "test.str", "hello", None)
    assert S.get_str(db, "test.str") == "hello"


def test_get_float(db):
    S.set_value(db, "test.float", 3.14, None)
    assert S.get_float(db, "test.float") == 3.14


def test_get_all_returns_dict(db):
    all_settings = S.get_all(db)
    assert "gamification.xp_save" in all_settings
    assert all_settings["gamification.xp_save"] == 1
