from pathlib import Path
from ipaddress import IPv4Network, IPv6Network, ip_network
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "annotations.db"
DOCUMENTS_DIR = DATA_DIR / "documents"
BACKUP_DIR = DATA_DIR / "backup"
EXPORTS_DIR = DATA_DIR / "exports"

# Frontend build output sink (owned by Vite; never committed).
# Used by backend/main.py to serve the SPA when the directory exists
# and DISABLE_SPA_MOUNT is not set.
STATIC_DIR = PROJECT_ROOT / "backend" / "static"

SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "anotasyon_session")
SESSION_MAX_AGE_SECONDS_RAW = os.environ.get(
    "SESSION_MAX_AGE_SECONDS",
    str(30 * 24 * 60 * 60),
)
try:
    SESSION_MAX_AGE_SECONDS = int(SESSION_MAX_AGE_SECONDS_RAW)
except ValueError:
    SESSION_MAX_AGE_SECONDS = 0
SESSION_COOKIE_SAMESITE = os.environ.get(
    "SESSION_COOKIE_SAMESITE",
    "none" if os.environ.get("SPACE_ID") else "lax",
).lower()

BACKUP_REPO_URL = os.environ.get("BACKUP_REPO_URL", "")
GITHUB_PAT = os.environ.get("GITHUB_PAT", "")
BOOTSTRAP_ADMIN_USERNAME = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "")

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
SPACE_ID = os.environ.get("SPACE_ID")

# Shared secret for the Mac-side `dqcheck predict-agent` ingest endpoints.
# Empty (the default) disables /api/internal/predictions* with HTTP 503.
DQCHECK_INGEST_TOKEN = os.environ.get("DQCHECK_INGEST_TOKEN", "")

# X-Forwarded-For trust. Off by default — the header is attacker-controlled
# in any direct-to-uvicorn deployment, and the IP is used for audit
# (user_sessions.ip_hash). Operators behind a trusted reverse proxy
# (Caddy, nginx, Cloudflare) flip this to "1" so XFF can be honored.
_trust_fwd = os.environ.get("TRUST_FORWARDED_FOR", "0") == "1"
TRUST_FORWARDED_FOR = _trust_fwd or SPACE_ID is not None
TRUSTED_PROXY_CIDRS_RAW = os.environ.get("TRUSTED_PROXY_CIDRS", "")


def _parse_proxy_cidrs(
    raw: str,
) -> tuple[tuple[IPv4Network | IPv6Network, ...], tuple[str, ...]]:
    networks: list[IPv4Network | IPv6Network] = []
    invalid: list[str] = []
    for value in (item.strip() for item in raw.split(",")):
        if not value:
            continue
        try:
            networks.append(ip_network(value, strict=False))
        except ValueError:
            invalid.append(value)
    return tuple(networks), tuple(invalid)


TRUSTED_PROXY_NETWORKS, INVALID_TRUSTED_PROXY_CIDRS = _parse_proxy_cidrs(
    TRUSTED_PROXY_CIDRS_RAW
)


def _parse_allowed_origins(raw: str) -> set[str]:
    """Comma-separated → cleaned set. Empty entries dropped, no normalization
    beyond strip — operators are responsible for matching scheme+host+port
    exactly as browsers will send."""
    return {o.strip() for o in raw.split(",") if o.strip()}


# CSRF defense via Origin/Referer allowlist (see backend/shared/csrf.py).
# Production requires this; dev/test bypass the middleware so the local
# TestClient + Vite dev server work without per-test header plumbing.
ALLOWED_ORIGINS: set[str] = _parse_allowed_origins(
    os.environ.get("ALLOWED_ORIGINS", "")
)

# Auto-detect Hugging Face Spaces and whitelist their domains
_space_id = SPACE_ID
if _space_id:
    try:
        # e.g. "barandncgz72/anotasyon-platform" -> author="barandncgz72", name="anotasyon-platform"
        if "/" in _space_id:
            author, name = _space_id.split("/", 1)
            # HF normalizes subdomains: replace underscores and dots with hyphens
            subdomain = f"{author.lower()}-{name.lower()}".replace("_", "-").replace(".", "-")
            ALLOWED_ORIGINS.add(f"https://{subdomain}.hf.space")
            ALLOWED_ORIGINS.add(f"https://{subdomain}.static.hf.space")
            # Browser Origin headers contain only scheme + authority, never
            # a Space path. The parent origin is needed for iframe embeds.
            ALLOWED_ORIGINS.add("https://huggingface.co")
            # Allow wildcard/bypass on Hugging Face Spaces to ensure requests can be made from anywhere.
            ALLOWED_ORIGINS.add("*")
    except Exception:
        pass

_VALID_ENVIRONMENTS = {"development", "test", "production"}


def is_production() -> bool:
    """True iff ENVIRONMENT env var is exactly 'production' (case-insensitive) or running on Hugging Face Spaces."""
    return ENVIRONMENT == "production" or SPACE_ID is not None


def validate_environment() -> None:
    """Raise RuntimeError if ENVIRONMENT is not one of the accepted values."""
    if ENVIRONMENT not in _VALID_ENVIRONMENTS:
        raise RuntimeError(
            f"ENVIRONMENT must be one of: {sorted(_VALID_ENVIRONMENTS)} "
            f"(got: {ENVIRONMENT!r})"
        )
    if SESSION_MAX_AGE_SECONDS <= 0:
        raise RuntimeError(
            "SESSION_MAX_AGE_SECONDS must be a positive integer "
            f"(got: {SESSION_MAX_AGE_SECONDS_RAW!r})"
        )
    if SESSION_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
        raise RuntimeError(
            "SESSION_COOKIE_SAMESITE must be one of: lax, strict, none "
            f"(got: {SESSION_COOKIE_SAMESITE!r})"
        )


def ensure_dirs() -> None:
    """Create all required data directories. Called from main.py lifespan."""
    for d in [DATA_DIR, DB_DIR, DOCUMENTS_DIR, BACKUP_DIR, EXPORTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
