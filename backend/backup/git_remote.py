"""Subprocess-driven git wrapper. Handles PAT URL construction, idempotent
init, commit + push with timeout and PAT scrubbing in error output."""
import logging
import re
import subprocess
from pathlib import Path


log = logging.getLogger(__name__)

# 30-second cap on every git invocation. Hung pushes (network stalls)
# raise TimeoutExpired which the orchestrator catches.
GIT_TIMEOUT = 30

# Clone is bounded separately because a fresh clone transfers the entire
# backup repo history, which can take longer than a single push of one
# changed file. 60s gives slow networks headroom without hanging the
# operator-driven restore command indefinitely.
CLONE_TIMEOUT = 60


class GitRemoteError(RuntimeError):
    """Wrapped git error with PAT scrubbed from message."""
    pass


def inject_pat(url: str, pat: str) -> str:
    """Return https URL with PAT injected as username, in the form
    https://x-access-token:<pat>@github.com/owner/repo.git.
    Idempotent: a URL that already has 'x-access-token:' is returned unchanged.
    Raises ValueError on non-https URLs (we don't support ssh)."""
    if not url.startswith("https://"):
        raise ValueError(f"only https URLs are supported, got: {url!r}")
    if "x-access-token:" in url:
        return url
    return url.replace("https://", f"https://x-access-token:{pat}@", 1)


_PAT_PATTERN = re.compile(r"x-access-token:[^@]+@")


def scrub_pat(text: str) -> str:
    """Replace any embedded PAT with x-access-token:*** for safe logging."""
    return _PAT_PATTERN.sub("x-access-token:***@", text)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Wrapper that always passes timeout, capture, text mode.
    Catches subprocess.TimeoutExpired and re-raises as GitRemoteError
    with the command argv PAT-scrubbed so error messages don't leak the
    token through stack traces or str(e)."""
    try:
        return subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        scrubbed_cmd = [scrub_pat(arg) for arg in cmd]
        raise GitRemoteError(
            f"git command timed out after {GIT_TIMEOUT}s: {scrubbed_cmd}"
        ) from None


def ensure_initialized(backup_dir: Path, remote_url: str, pat: str) -> None:
    """If `backup_dir/.git` exists, no-op (idempotent — does NOT re-validate
    the configured remote, so an operator who changes BACKUP_REPO_URL mid-
    deployment must `rm -rf <backup_dir>/.git` to pick up the new remote).
    Otherwise:
       - git init -b main
       - configure user.email + user.name
       - commit --allow-empty -m "init" (so HEAD exists before first push)
       - git remote add origin <pat-injected-url>
    Raises GitRemoteError if any step fails (so the caller doesn't see a
    half-initialized .git directory).
    """
    if (backup_dir / ".git").exists():
        return

    backup_dir.mkdir(parents=True, exist_ok=True)
    pat_url = inject_pat(remote_url, pat)

    def _check(cmd_for_log: str, result: subprocess.CompletedProcess) -> None:
        if result.returncode != 0:
            stderr = scrub_pat(result.stderr or "")
            raise GitRemoteError(f"{cmd_for_log} failed: {stderr}")

    _check("git init", _run(["git", "init", "-b", "main"], cwd=backup_dir))
    _check("git config email", _run(["git", "config", "user.email", "backup@localhost"], cwd=backup_dir))
    _check("git config name", _run(["git", "config", "user.name", "Backup Bot"], cwd=backup_dir))
    _check("git commit init", _run(["git", "commit", "--allow-empty", "-m", "init"], cwd=backup_dir))
    _check("git remote add", _run(["git", "remote", "add", "origin", pat_url], cwd=backup_dir))


def commit_and_push(backup_dir: Path, message: str) -> str:
    """git add . → git commit (allow-empty so empty cycles still tag a HEAD)
    → git push origin main (fall back to master on src-refspec failure).
    Returns the resulting commit SHA. Raises GitRemoteError on push failure
    after PAT-scrubbing the captured stderr."""
    _run(["git", "add", "."], cwd=backup_dir)
    _run(["git", "commit", "--allow-empty", "-m", message], cwd=backup_dir)

    sha_proc = _run(["git", "rev-parse", "HEAD"], cwd=backup_dir)
    sha = sha_proc.stdout.strip()

    push = _run(["git", "push", "origin", "main"], cwd=backup_dir)
    if push.returncode != 0:
        main_stderr = scrub_pat(push.stderr or "")
        if "src refspec main" in push.stderr:
            push = _run(["git", "push", "origin", "master"], cwd=backup_dir)
        if push.returncode != 0:
            stderr = scrub_pat(push.stderr or "")
            # Combine both stderrs so we don't lose the main attempt's diagnostic
            combined = (
                f"main: {main_stderr} | master: {stderr}"
                if "src refspec main" in main_stderr
                else stderr
            )
            raise GitRemoteError(f"git push failed: {combined}")

    return sha
