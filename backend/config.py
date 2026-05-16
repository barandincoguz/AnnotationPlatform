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

_VALID_ENVIRONMENTS = {"development", "test", "production"}


def is_production() -> bool:
    """True iff ENVIRONMENT env var is exactly 'production' (case-insensitive)."""
    return ENVIRONMENT == "production"


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
