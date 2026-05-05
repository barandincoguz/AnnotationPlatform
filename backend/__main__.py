"""Allow `python -m backend.cli ...` invocation.

This file is intentionally minimal — see backend/cli.py for the actual logic.
"""
from backend.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
