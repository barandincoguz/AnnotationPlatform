"""Production-mode secret enforcement.

Called from lifespan startup BEFORE DB work so misconfigured deploys
fail fast and loud (Docker Compose restart loop will keep retrying,
but stderr makes diagnosis trivial).
"""
import sys

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


def enforce_production_secrets() -> None:
    """In ENVIRONMENT=production: hard-fail on any unsafe config.

    Otherwise: no-op.
    """
    if config.ENVIRONMENT != "production":
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

    if errors:
        msg = "production mode enforcement failed:\n  - " + "\n  - ".join(errors)
        msg += "\nSet ENVIRONMENT=development to disable enforcement."
        raise ProductionConfigError(msg)

    if not config.BACKUP_REPO_URL:
        print(
            "WARNING: no backup configured (BACKUP_REPO_URL empty); "
            "set it for automatic GitHub backup.",
            file=sys.stderr,
        )
