from pathlib import Path
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

BACKUP_REPO_URL = os.environ.get("BACKUP_REPO_URL", "")
GITHUB_PAT = os.environ.get("GITHUB_PAT", "")
BOOTSTRAP_ADMIN_USERNAME = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "")

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")

# X-Forwarded-For trust. Off by default — the header is attacker-controlled
# in any direct-to-uvicorn deployment, and the IP is used for audit
# (user_sessions.ip_hash). Operators behind a trusted reverse proxy
# (Caddy, nginx, Cloudflare) flip this to "1" so XFF can be honored.
TRUST_FORWARDED_FOR = os.environ.get("TRUST_FORWARDED_FOR", "0") == "1"


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
_space_id = os.environ.get("SPACE_ID")
if _space_id:
    try:
        # e.g. "barandncgz72/anotasyon-platform" -> author="barandncgz72", name="anotasyon-platform"
        if "/" in _space_id:
            author, name = _space_id.split("/", 1)
            # HF normalizes subdomains: replace underscores and dots with hyphens
            subdomain = f"{author.lower()}-{name.lower()}".replace("_", "-").replace(".", "-")
            ALLOWED_ORIGINS.add(f"https://{subdomain}.hf.space")
            # Also whitelist direct domain variants and huggingface.co for iframe embeds
            ALLOWED_ORIGINS.add("https://huggingface.co")
            ALLOWED_ORIGINS.add(f"https://huggingface.co/spaces/{_space_id}")
    except Exception:
        pass

_VALID_ENVIRONMENTS = {"development", "test", "production"}


def is_production() -> bool:
    """True iff ENVIRONMENT env var is exactly 'production' (case-insensitive) or running on Hugging Face Spaces."""
    return ENVIRONMENT == "production" or os.environ.get("SPACE_ID") is not None


def validate_environment() -> None:
    """Raise RuntimeError if ENVIRONMENT is not one of the accepted values."""
    if ENVIRONMENT not in _VALID_ENVIRONMENTS:
        raise RuntimeError(
            f"ENVIRONMENT must be one of: {sorted(_VALID_ENVIRONMENTS)} "
            f"(got: {ENVIRONMENT!r})"
        )


def ensure_dirs() -> None:
    """Create all required data directories. Called from main.py lifespan."""
    for d in [DATA_DIR, DB_DIR, DOCUMENTS_DIR, BACKUP_DIR, EXPORTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
