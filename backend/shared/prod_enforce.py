"""Production-mode secret enforcement.

Called from lifespan startup BEFORE DB work so misconfigured deploys
fail fast and loud (Docker Compose restart loop will keep retrying,
but stderr makes diagnosis trivial).
"""
from urllib.parse import urlsplit

from backend import config


DEV_SESSION_SECRETS = {
    "dev-secret-DO-NOT-USE-IN-PROD",  # backend/config.py default
    "dev-secret-change-me",            # docker-compose.yml default
}

_MIN_SESSION_SECRET_LEN = 32
_MIN_BOOTSTRAP_PASSWORD_LEN = 12

# Passwords that pass the length gate but are obvious placeholders.
# These names appear in committed examples / Stack Overflow snippets
# and are tried first by any post-deploy scan. Substring match against
# the lowercase password — "admin123456789" passes the length check but
# trips this list at the "admin" substring.
_PLACEHOLDER_PASSWORD_PATTERNS = (
    "admin",
    "password",
    "letmein",
    "changeme",
    "replace_me",
    "replaceme",
    "qwerty",
)

# .env.example ships its REQUIRED rows as `<REPLACE_ME_*>` placeholders so
# an operator who copies the file verbatim is forced to edit each one.
# The placeholders happen to be ≥32 chars and absent from
# DEV_SESSION_SECRETS, so SESSION_SECRET would otherwise sail past both
# checks — leaving the deploy running on a publicly-known constant from
# the repo. Reject any value containing this needle (case-insensitive) in
# the env vars that are too long for a simple equality whitelist.
_TEMPLATE_PLACEHOLDER_NEEDLE = "<replace_me"


class ProductionConfigError(RuntimeError):
    """Raised when production mode is enabled but config is unsafe."""


def _validate_github_backup_url(url: str) -> str | None:
    """Return a production-safety error for an invalid GitHub backup remote."""
    if any(char.isspace() for char in url):
        return "must not contain whitespace"
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "is not a valid URL"

    if parsed.scheme != "https":
        return "must use https"
    if parsed.hostname != "github.com":
        return "must point to github.com"
    if parsed.username is not None or parsed.password is not None:
        return "must not contain credentials; set GITHUB_PAT separately"
    if parsed.query or parsed.fragment:
        return "must not contain query or fragment"

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        return "must use GitHub remote format https://github.com/<owner>/<repo>.git"
    if parts[1] in {"", ".git"}:
        return "must include a repository name"
    if not parts[1].endswith(".git"):
        return "must use GitHub remote format https://github.com/<owner>/<repo>.git"
    return None


def _validate_public_origin(origin: str) -> str | None:
    """Return a production-safety error for an invalid browser origin."""
    if any(char.isspace() for char in origin):
        return "must not contain whitespace"
    if "*" in origin:
        return "must not contain wildcards"

    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return "contains an invalid host or port"

    if parsed.scheme != "https":
        return "must use https"
    if not parsed.hostname:
        return "must include a host"
    if parsed.username is not None or parsed.password is not None:
        return "must not contain credentials"
    if parsed.path or parsed.query or parsed.fragment:
        return "must be an exact origin without path, query, or fragment"

    default_port = port in (None, 443)
    canonical_host = parsed.hostname.lower()
    if ":" in canonical_host:
        canonical_host = f"[{canonical_host}]"
    canonical = f"https://{canonical_host}"
    if not default_port:
        canonical += f":{port}"
    if origin != canonical:
        return f"must use canonical form {canonical!r}"
    return None


def enforce_production_secrets() -> None:
    """In ENVIRONMENT=production: hard-fail on any unsafe config.

    Otherwise: no-op.
    """
    if not config.is_production():
        return

    errors: list[str] = []

    if config.SESSION_SECRET in DEV_SESSION_SECRETS:
        errors.append(
            "SESSION_SECRET must not be the default placeholder "
            "(set via env var; generate with `openssl rand -hex 32`)"
        )
    elif _TEMPLATE_PLACEHOLDER_NEEDLE in config.SESSION_SECRET.lower():
        errors.append(
            "SESSION_SECRET still contains the .env.example template "
            f"placeholder ({_TEMPLATE_PLACEHOLDER_NEEDLE!r}); generate a "
            "real value via `openssl rand -hex 32`"
        )
    elif len(config.SESSION_SECRET) < _MIN_SESSION_SECRET_LEN:
        errors.append(
            f"SESSION_SECRET must be at least {_MIN_SESSION_SECRET_LEN} characters "
            f"(current: {len(config.SESSION_SECRET)})"
        )

    if config.BOOTSTRAP_ADMIN_PASSWORD and \
            len(config.BOOTSTRAP_ADMIN_PASSWORD) < _MIN_BOOTSTRAP_PASSWORD_LEN:
        errors.append(
            f"BOOTSTRAP_ADMIN_PASSWORD must be at least "
            f"{_MIN_BOOTSTRAP_PASSWORD_LEN} characters in production"
        )

    # Block obvious placeholder passwords even when they meet the length
    # gate (e.g. "admin123456789" — flagged because pre-deploy scans
    # try patterns like this first; see SECURITY notes in .env.example).
    if config.BOOTSTRAP_ADMIN_PASSWORD:
        lowered = config.BOOTSTRAP_ADMIN_PASSWORD.lower()
        for needle in _PLACEHOLDER_PASSWORD_PATTERNS:
            if needle in lowered:
                errors.append(
                    f"BOOTSTRAP_ADMIN_PASSWORD contains a placeholder "
                    f"substring ({needle!r}); choose an un-guessable value"
                )
                break

    if not config.ALLOWED_ORIGINS:
        errors.append(
            "ALLOWED_ORIGINS must be set in production (comma-separated "
            "full origins; see backend/shared/csrf.py). Without it every "
            "state-changing request is rejected."
        )
    elif any(
        _TEMPLATE_PLACEHOLDER_NEEDLE in origin.lower()
        for origin in config.ALLOWED_ORIGINS
    ):
        errors.append(
            "ALLOWED_ORIGINS still contains the .env.example template "
            f"placeholder ({_TEMPLATE_PLACEHOLDER_NEEDLE!r}); set the real "
            "public origin (e.g. https://anotasyon.example.com)"
        )
    else:
        invalid_origins = [
            (origin, error)
            for origin in sorted(config.ALLOWED_ORIGINS)
            if (error := _validate_public_origin(origin)) is not None
        ]
        for origin, error in invalid_origins:
            errors.append(f"ALLOWED_ORIGINS entry {origin!r} {error}")

    if config.INVALID_TRUSTED_PROXY_CIDRS:
        errors.append(
            "TRUSTED_PROXY_CIDRS contains invalid network values: "
            + ", ".join(repr(value) for value in config.INVALID_TRUSTED_PROXY_CIDRS)
        )
    if any(network.prefixlen == 0 for network in config.TRUSTED_PROXY_NETWORKS):
        errors.append(
            "TRUSTED_PROXY_CIDRS must not trust an entire address family "
            "(0.0.0.0/0 or ::/0)"
        )
    if (
        config.TRUST_FORWARDED_FOR
        and not config.TRUSTED_PROXY_NETWORKS
    ):
        errors.append(
            "TRUST_FORWARDED_FOR=1 requires TRUSTED_PROXY_CIDRS in production; "
            "otherwise clients can forge rate-limit and audit IPs"
        )

    if not config.BACKUP_REPO_URL:
        errors.append(
            "BACKUP_REPO_URL must be set in production so off-host GitHub "
            "backups are mandatory"
        )
    else:
        backup_url_error = _validate_github_backup_url(config.BACKUP_REPO_URL)
        if backup_url_error is not None:
            errors.append(f"BACKUP_REPO_URL {backup_url_error}")

    if not config.GITHUB_PAT:
        errors.append(
            "GITHUB_PAT must be set in production so GitHub backup pushes "
            "cannot be silently skipped"
        )

    if errors:
        msg = "production mode enforcement failed:\n  - " + "\n  - ".join(errors)
        msg += "\nSet ENVIRONMENT=development to disable enforcement."
        raise ProductionConfigError(msg)
