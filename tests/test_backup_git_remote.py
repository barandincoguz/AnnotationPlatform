"""Tests for backend.backup.git_remote — subprocess-driven git wrapper."""
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import pytest


def test_inject_pat_https_url():
    from backend.backup.git_remote import inject_pat
    out = inject_pat("https://github.com/owner/repo.git", "secret123")
    assert out == "https://x-access-token:secret123@github.com/owner/repo.git"


def test_inject_pat_idempotent_does_not_double_inject():
    """If the URL already contains a PAT, return it unchanged."""
    from backend.backup.git_remote import inject_pat
    already = "https://x-access-token:abc@github.com/owner/repo.git"
    out = inject_pat(already, "different")
    assert out == already


def test_inject_pat_raises_on_non_https():
    from backend.backup.git_remote import inject_pat
    with pytest.raises(ValueError):
        inject_pat("git@github.com:owner/repo.git", "secret")


def test_scrub_pat_removes_token_from_text():
    from backend.backup.git_remote import scrub_pat
    raw = "fatal: Authentication failed for 'https://x-access-token:abc123@github.com/owner/repo/'"
    out = scrub_pat(raw)
    assert "abc123" not in out
    assert "x-access-token:***" in out


def test_ensure_initialized_creates_git_dir(tmp_path):
    from backend.backup.git_remote import ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    assert (backup_dir / ".git").exists()
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=backup_dir,
        capture_output=True, text=True,
    )
    assert log.returncode == 0
    assert "init" in log.stdout


def test_ensure_initialized_is_idempotent(tmp_path):
    from backend.backup.git_remote import ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    # Second call should not raise or duplicate the init commit
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=backup_dir,
        capture_output=True, text=True,
    )
    # Still exactly one commit
    assert log.stdout.count("\n") == 1


def test_ensure_initialized_does_not_store_pat_in_git_config(tmp_path):
    from backend.backup.git_remote import ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    ensure_initialized(
        backup_dir,
        "https://github.com/owner/repo.git",
        "supersecret",
    )

    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=backup_dir,
        capture_output=True, text=True,
    )
    assert remote.returncode == 0
    assert remote.stdout.strip() == "https://github.com/owner/repo.git"
    assert "supersecret" not in (backup_dir / ".git" / "config").read_text()


def test_ensure_initialized_refreshes_existing_origin_without_pat(tmp_path):
    from backend.backup.git_remote import ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    ensure_initialized(
        backup_dir,
        "https://github.com/owner/old.git",
        "oldsecret",
    )
    ensure_initialized(
        backup_dir,
        "https://github.com/owner/new.git",
        "newsecret",
    )

    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=backup_dir,
        capture_output=True, text=True,
    )
    assert remote.returncode == 0
    assert remote.stdout.strip() == "https://github.com/owner/new.git"
    assert "oldsecret" not in (backup_dir / ".git" / "config").read_text()
    assert "newsecret" not in (backup_dir / ".git" / "config").read_text()


def _completed(cmd, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=cmd,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


@pytest.mark.parametrize(
    ("failing_prefix", "expected_label"),
    [
        (("git", "add"), "git add"),
        (("git", "commit"), "git commit"),
        (("git", "rev-parse"), "git rev-parse"),
    ],
)
def test_commit_and_push_raises_when_pre_push_command_fails(
    tmp_path,
    failing_prefix,
    expected_label,
):
    from backend.backup.git_remote import GitRemoteError, commit_and_push
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()

    def fake_run(cmd, cwd):
        if tuple(cmd[:len(failing_prefix)]) == failing_prefix:
            return _completed(
                cmd,
                returncode=1,
                stderr=(
                    "fatal: https://x-access-token:supersecret@"
                    "github.com/owner/repo.git failed"
                ),
            )
        if cmd[:2] == ["git", "rev-parse"]:
            return _completed(cmd, stdout="oldsha\n")
        return _completed(cmd)

    with patch("backend.backup.git_remote._run", side_effect=fake_run):
        with pytest.raises(GitRemoteError) as exc:
            commit_and_push(backup_dir, "test")

    message = str(exc.value)
    assert expected_label in message
    assert "supersecret" not in message
    assert "x-access-token:***" in message


def test_commit_and_push_runs_subprocess_with_timeout(tmp_path):
    """Verify commit_and_push invokes git push with the 30s timeout."""
    from backend.backup.git_remote import commit_and_push, ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    (backup_dir / "x.json").write_text("{}")

    captured_calls = []
    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        captured_calls.append((args, kwargs))
        if args[0][:2] == ["git", "push"]:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result
        return real_run(*args, **kwargs)

    with patch("backend.backup.git_remote.subprocess.run", side_effect=fake_run):
        sha = commit_and_push(backup_dir, "test commit")

    assert isinstance(sha, str) and len(sha) >= 7
    push_calls = [c for c in captured_calls if c[0][0][:2] == ["git", "push"]]
    assert len(push_calls) == 1
    assert push_calls[0][1].get("timeout") == 30


def test_commit_and_push_falls_back_to_master(tmp_path):
    """If 'git push origin main' fails with 'src refspec main', retry with master."""
    from backend.backup.git_remote import commit_and_push, ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    (backup_dir / "x.json").write_text("{}")

    real_run = subprocess.run
    push_attempts = []

    def fake_run(*args, **kwargs):
        cmd = args[0]
        if cmd[:2] == ["git", "push"]:
            push_attempts.append(cmd)
            result = MagicMock()
            if "main" in cmd:
                result.returncode = 1
                result.stdout = ""
                result.stderr = "error: src refspec main does not match any"
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result
        return real_run(*args, **kwargs)

    with patch("backend.backup.git_remote.subprocess.run", side_effect=fake_run):
        sha = commit_and_push(backup_dir, "test")

    assert len(push_attempts) == 2
    assert "main" in push_attempts[0]
    assert "master" in push_attempts[1]
    assert isinstance(sha, str)


def test_commit_and_push_raises_on_real_failure(tmp_path):
    """Auth failures (or any non-refspec error) should raise."""
    from backend.backup.git_remote import commit_and_push, ensure_initialized
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    ensure_initialized(backup_dir, "https://github.com/owner/repo.git", "pat")
    (backup_dir / "x.json").write_text("{}")

    real_run = subprocess.run

    def fake_run(*args, **kwargs):
        cmd = args[0]
        if cmd[:2] == ["git", "push"]:
            result = MagicMock()
            result.returncode = 128
            result.stdout = ""
            result.stderr = "remote: Permission denied"
            return result
        return real_run(*args, **kwargs)

    with patch("backend.backup.git_remote.subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc:
            commit_and_push(backup_dir, "test")
        assert "Permission denied" in str(exc.value)
        assert "pat" not in str(exc.value).lower() or "x-access-token:***" in str(exc.value)


def test_run_scrubs_pat_from_timeout_error(tmp_path):
    """If a git command times out and the PAT is in argv, the raised
    error must NOT contain the raw PAT."""
    from backend.backup.git_remote import _run, GitRemoteError, GIT_TIMEOUT
    from unittest.mock import patch

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=GIT_TIMEOUT)

    pat_argv = [
        "git", "remote", "add", "origin",
        "https://x-access-token:supersecret@github.com/o/r.git",
    ]
    with patch("backend.backup.git_remote.subprocess.run", side_effect=fake_run):
        with pytest.raises(GitRemoteError) as exc:
            _run(pat_argv, tmp_path)
    msg = str(exc.value)
    assert "supersecret" not in msg
    assert "x-access-token:***" in msg
