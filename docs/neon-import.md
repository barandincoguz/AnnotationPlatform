# Neon Postgres → SQLite import runbook

One-time ETL to pull `özelge` rows from a remote Neon Postgres database into
this project's SQLite via the existing `ingest_file` pipeline.

**Scope:** Read-only against the source. Discovery-first: schema + a sanitized
sample row before any mapping decision. All sensitive artifacts land in
gitignored paths (`docs/external/`, `data/import-neon/`, `.env.local`).

---

## Phase 1 — Discovery

### Step 1: Read-only role in Neon

Open Neon's SQL editor as the admin user. Run once:

```sql
-- Replace the password with a strong random one (e.g. `openssl rand -hex 24`).
CREATE ROLE schema_reader WITH LOGIN PASSWORD '<STRONG_RANDOM_PASSWORD>';

-- Grant browse access to the schema that holds the özelge tables.
-- If the data lives in a non-`public` schema, swap `public` for that name.
GRANT USAGE ON SCHEMA public TO schema_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO schema_reader;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO schema_reader;

-- Cover tables created after this role is granted.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO schema_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO schema_reader;
```

Verify from Neon's editor:

```sql
-- Should list the tables; no INSERT/UPDATE/DELETE allowed for this role.
SET ROLE schema_reader;
SELECT table_name FROM information_schema.tables WHERE table_schema='public';
RESET ROLE;
```

### Step 2: Connection string → `.env.local`

Neon shows a connection string per role under *Connection details*. Copy it
for `schema_reader` and save **locally only**:

```bash
# .env.local  (gitignored — never paste in chat or commit)
NEON_RO_URL="postgresql://schema_reader:<password>@ep-xxx.neon.tech/<dbname>?sslmode=require"
```

`sslmode=require` is mandatory — Neon refuses unencrypted connections.

### Step 3: Install `pg_dump` client (macOS)

```bash
brew install libpq
# Add to your shell rc so the binaries stay on PATH:
echo 'export PATH="/opt/homebrew/opt/libpq/bin:$PATH"' >> ~/.zshrc
exec zsh -l
```

Sanity check:

```bash
pg_dump --version          # should print 16.x or 17.x
```

### Step 4: Schema-only dump

```bash
source .env.local
pg_dump --schema-only --no-owner --no-privileges --no-acl \
  "$NEON_RO_URL" > docs/external/neon-schema.sql
```

Output lands in the gitignored `docs/external/` directory. Open it locally,
identify the table(s) holding özelge rows + their columns, then move to the
mapping spec below.

### Step 5: One sanitized sample row per candidate table

Just enough to understand the columns. Example for a hypothetical `ozelgeler`
table — adapt the column list once Step 4 reveals the real schema:

```bash
psql "$NEON_RO_URL" -c "
  SELECT json_build_object(
    'evrak_oid', evrak_oid,
    'sayi', sayi,
    'tarih', tarih,
    'konu', LEFT(COALESCE(konu, ''), 80) || '...',
    'has_pdf_text', length(COALESCE(pdf_text, '')) > 0,
    'pdf_text_chars', length(COALESCE(pdf_text, ''))
  )
  FROM ozelgeler
  LIMIT 1;
"
```

Save sanitized output to `docs/external/neon-sample.txt` (gitignored) for the
mapping discussion. **Do not** paste raw row content into chat — column names
and lengths are enough.

---

## Phase 1.5 — Mapping spec

Target shape (matches `backend/documents/parser.py` — the existing ingest
contract):

```jsonc
{
  "evrakOid": "string, required",       // → documents_meta.document_id
  "pdfText": "string",                  // → documents_meta.pdf_text (required OR htmlText)
  "htmlText": "string | null",          // fallback when pdfText empty
  "sayi": "int | null",
  "tarih": "string | null, YYYYMMDD",
  "basvuruTarihi": "string | null",
  "vergiTuru": "string | null",
  "vergiDonemi": "string | null",
  "konu": "string | null",
  "mukellefiyetTuru": "string | null",
  "kanunBilgileri": [
    {"kanunKodu": "string", "kanunMaddesi": "string", "kanunMaddesiTuru": "string"}
  ],
  "bkkTebligSirkuBilgileri": [
    {"turu": "string", "kanunKodu": "string", "maddeNo": "string"}
  ]
}
```

Fill the mapping table once Neon columns are known:

| Target (JSON key) | Neon column | Notes / transform |
|---|---|---|
| `evrakOid` | `?` | required — must be unique per row |
| `pdfText` | `?` | required (OR htmlText). If Neon has the raw PDF blob, we'll need to extract first. |
| `tarih` | `?` | Postgres `date` → `YYYYMMDD` string (`to_char(tarih, 'YYYYMMDD')`) |
| `sayi` | `?` | integer cast |
| `konu` | `?` | direct |
| `vergiTuru` | `?` | direct |
| `kanunBilgileri[]` | `?` | likely a join table or JSONB column |
| `bkkTebligSirkuBilgileri[]` | `?` | likely a join table or JSONB column |

---

## Phase 2 — ETL execution

### Step 6: Install Python client

```bash
.venv/bin/pip install 'psycopg[binary]>=3.2'
```

### Step 7: Streaming export

A small script reads from Neon in chunks (server-side cursor), shapes each row
into the JSON contract above, and writes one file per chunk into
`data/import-neon/`. Sketched skeleton:

```python
# scripts/neon_import.py — created after the mapping spec is finalized
import json, os, pathlib, psycopg

OUT = pathlib.Path("data/import-neon")
OUT.mkdir(parents=True, exist_ok=True)
CHUNK = 1000

with psycopg.connect(os.environ["NEON_RO_URL"]) as conn, conn.cursor(name="ozelge_cur") as cur:
    cur.itersize = CHUNK
    cur.execute("SELECT ... FROM ozelgeler ORDER BY <stable_key>")  # finalised after mapping
    chunk_idx = 0
    batch: list[dict] = []
    for row in cur:
        batch.append(shape_row(row))  # mapping from Step 5
        if len(batch) >= CHUNK:
            (OUT / f"neon-{chunk_idx:05d}.json").write_text(
                json.dumps(batch, ensure_ascii=False), encoding="utf-8"
            )
            chunk_idx += 1
            batch.clear()
    if batch:
        (OUT / f"neon-{chunk_idx:05d}.json").write_text(
            json.dumps(batch, ensure_ascii=False), encoding="utf-8"
        )
```

### Step 8: Pilot ingest (N≈10)

```bash
# Cap psycopg cursor on a small slice first — verify shape before going wide.
.venv/bin/python -m scripts.neon_import --limit 10
.venv/bin/python -m backend.cli ingest-dir data/import-neon/
```

Spot-check 2-3 docs against the source row.

### Step 9: Full run + audit

```bash
.venv/bin/python -m scripts.neon_import         # no limit
.venv/bin/python -m backend.cli ingest-dir data/import-neon/

# Counts: Neon source vs. ingested SQLite rows
psql "$NEON_RO_URL" -c "SELECT COUNT(*) FROM ozelgeler"
sqlite3 data/db/annotations.db "SELECT COUNT(*) FROM documents_meta"
```

Mismatches show up as parser skips in the ingest log — `ParseError` rows
print at WARNING. Re-run the importer with `--only <evrakOid>` for any
skipped doc to inspect locally.

---

## Cleanup

After the ingest is verified:

```bash
# Optional: rotate the read-only role in Neon (revoke + drop) once the
# pull is done — single-use credential, single-use lifecycle.
psql "$NEON_ADMIN_URL" -c "DROP ROLE schema_reader"

# Local artifacts stay gitignored under docs/external/ + data/import-neon/.
# Wipe them when no longer needed for debugging:
rm -rf docs/external/neon-*.sql docs/external/neon-sample.txt
rm -rf data/import-neon/
```

---

## Security checklist

- [ ] `schema_reader` role has **only** `USAGE` + `SELECT` (no `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`).
- [ ] `.env.local` is gitignored and never pasted in chat.
- [ ] `sslmode=require` on every connection string.
- [ ] Schema dump + sample row land in gitignored `docs/external/`.
- [ ] Role rotated/dropped after the one-time pull.
- [ ] No raw row content shared in chat — only column names, types, sanitized samples.
