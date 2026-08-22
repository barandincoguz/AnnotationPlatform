from types import SimpleNamespace

from backend import cli, config


def test_seed_e2e_cannot_be_forced_in_production(tmp_path, monkeypatch):
    target = tmp_path / "annotations.db"
    monkeypatch.setattr(config, "DB_PATH", target)
    monkeypatch.setattr(config, "is_production", lambda: True)

    result = cli.cmd_seed_e2e(SimpleNamespace(reset=True, force=True))

    assert result == 2
    assert not target.exists()
