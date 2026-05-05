FROM python:3.11-slim

WORKDIR /app

# System deps for bcrypt (uses libffi)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python deps first for layer caching
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Application
COPY backend/ ./backend/

# Editable install so `python -m backend.cli` works
RUN pip install --no-cache-dir -e .

# Data volume mount point
VOLUME ["/data"]
ENV DATA_DIR=/data

EXPOSE 8000

# Apply migrations then start uvicorn
CMD ["sh", "-c", "python -m backend.cli migrate && uvicorn backend.main:app --host 0.0.0.0 --port 8000"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" || exit 1
