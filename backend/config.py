from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "annotations.db"
DOCUMENTS_DIR = DATA_DIR / "documents"
BACKUP_DIR = DATA_DIR / "backup"
EXPORTS_DIR = DATA_DIR / "exports"

SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-secret-DO-NOT-USE-IN-PROD")
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "anotasyon_session")

BACKUP_REPO_URL = os.environ.get("BACKUP_REPO_URL", "")
GITHUB_PAT = os.environ.get("GITHUB_PAT", "")
BOOTSTRAP_ADMIN_USERNAME = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "")

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


def ensure_dirs() -> None:
    """Create all required data directories. Called from main.py lifespan."""
    for d in [DATA_DIR, DB_DIR, DOCUMENTS_DIR, BACKUP_DIR, EXPORTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
