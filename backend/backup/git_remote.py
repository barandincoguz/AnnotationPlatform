"""Subprocess-driven git wrapper. Handles PAT URL construction, idempotent
init, commit + push with timeout and PAT scrubbing in error output."""
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional


log = logging.getLogger(__name__)

# 120-second cap on every git invocation. Hung pushes (network stalls)
# raise TimeoutExpired which the orchestrator catches. Increased to 120
# to handle large JSON snapshots safely over slow networks.
GIT_TIMEOUT = 120

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
_PAT_URL_PREFIX = re.compile(r"^https://x-access-token:[^@]+@")


def remote_url_without_pat(url: str) -> str:
    """Return the HTTPS remote URL with any x-access-token credential removed."""
    if not url.startswith("https://"):
        raise ValueError(f"only https URLs are supported, got: {url!r}")
    return _PAT_URL_PREFIX.sub("https://", url)


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


def _check(cmd_for_log: str, result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0:
        stderr = scrub_pat(result.stderr or result.stdout or "")
        raise GitRemoteError(f"{cmd_for_log} failed: {stderr}")


def _ensure_origin_remote(backup_dir: Path, remote_url: str) -> None:
    plain_url = remote_url_without_pat(remote_url)
    current = _run(["git", "remote", "get-url", "origin"], cwd=backup_dir)
    if current.returncode == 0:
        current_url = current.stdout.strip()
        if current_url != plain_url:
            _check(
                "git remote set-url",
                _run(["git", "remote", "set-url", "origin", plain_url], cwd=backup_dir),
            )
        return

    _check(
        "git remote add",
        _run(["git", "remote", "add", "origin", plain_url], cwd=backup_dir),
    )


def _has_payload_files(backup_dir: Path) -> bool:
    return any(path.name != ".git" for path in backup_dir.iterdir())


def _is_missing_remote_ref(result: subprocess.CompletedProcess) -> bool:
    text = (result.stderr or result.stdout or "").lower()
    return "couldn't find remote ref" in text or "could not find remote ref" in text


def _adopt_existing_remote_history(
    backup_dir: Path,
    remote_url: str,
    pat: str,
) -> bool:
    """Attach a fresh backup worktree to an existing GitHub branch.

    GitHub rejects the first push when the private backup repo already has
    commits (for example a README) and the local backup dir starts from an
    unrelated root commit. Fetching the remote branch and soft-resetting HEAD
    preserves the freshly written snapshot files while making the next backup
    commit a normal child of the remote history.
    """
    auth_url = inject_pat(remote_url_without_pat(remote_url), pat)
    for branch in ("main", "master"):
        fetched = _run(["git", "fetch", "--depth=1", auth_url, branch], cwd=backup_dir)
        if fetched.returncode == 0:
            _check(
                "git symbolic-ref",
                _run(["git", "symbolic-ref", "HEAD", f"refs/heads/{branch}"], cwd=backup_dir),
            )
            _check(
                "git reset --soft",
                _run(["git", "reset", "--soft", "FETCH_HEAD"], cwd=backup_dir),
            )
            return True
        if _is_missing_remote_ref(fetched):
            continue
        _check(f"git fetch {branch}", fetched)

    return False


def ensure_initialized(backup_dir: Path, remote_url: str, pat: str) -> None:
    """Ensure `backup_dir` is a git repo with origin set to the plain remote URL.

    If `backup_dir/.git` exists, refresh origin if BACKUP_REPO_URL changed.
    The PAT is never stored in `.git/config`; push authentication passes it
    directly to `git push`.

    Otherwise:
       - git init -b main
       - configure user.email + user.name
       - commit --allow-empty -m "init" (so HEAD exists before first push)
       - git remote add origin <plain-https-url>
    Raises GitRemoteError if any step fails (so the caller doesn't see a
    half-initialized .git directory).
    """
    remote_url_without_pat(remote_url)
    if (backup_dir / ".git").exists():
        _ensure_origin_remote(backup_dir, remote_url)
        return

    backup_dir.mkdir(parents=True, exist_ok=True)

    _check("git init", _run(["git", "init", "-b", "main"], cwd=backup_dir))
    _check("git config email", _run(["git", "config", "user.email", "backup@localhost"], cwd=backup_dir))
    _check("git config name", _run(["git", "config", "user.name", "Backup Bot"], cwd=backup_dir))
    _ensure_origin_remote(backup_dir, remote_url)
    adopted = (
        _adopt_existing_remote_history(backup_dir, remote_url, pat)
        if _has_payload_files(backup_dir)
        else False
    )
    if not adopted:
        _check("git commit init", _run(["git", "commit", "--allow-empty", "-m", "init"], cwd=backup_dir))


def commit_and_push(
    backup_dir: Path,
    message: str,
    *,
    remote_url: Optional[str] = None,
    pat: Optional[str] = None,
) -> str:
    """git add . → git commit (allow-empty so empty cycles still tag a HEAD)
    → git push origin main (fall back to master on src-refspec failure).
    Returns the resulting commit SHA. Raises GitRemoteError on push failure
    after PAT-scrubbing the captured stderr."""
    _check("git add", _run(["git", "add", "."], cwd=backup_dir))
    _check(
        "git commit",
        _run(["git", "commit", "--allow-empty", "-m", message], cwd=backup_dir),
    )

    sha_proc = _run(["git", "rev-parse", "HEAD"], cwd=backup_dir)
    _check("git rev-parse", sha_proc)
    sha = sha_proc.stdout.strip()

    push_target = (
        inject_pat(remote_url_without_pat(remote_url), pat)
        if remote_url and pat
        else "origin"
    )
    push = _run(["git", "push", push_target, "main"], cwd=backup_dir)
    if push.returncode != 0:
        main_stderr = scrub_pat(push.stderr or "")
        if "src refspec main" in (push.stderr or ""):
            push = _run(["git", "push", push_target, "master"], cwd=backup_dir)
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
