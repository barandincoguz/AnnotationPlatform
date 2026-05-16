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
