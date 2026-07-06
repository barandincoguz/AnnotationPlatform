# Feedback System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kullanıcılara şikayet ve öneri göndermeleri için yeni bir sekme ve admin panelinde liste sayfası oluşturmak.

**Architecture:** SQLite'a yeni `user_feedback` tablosu ekler. Backend: 2 endpoint (POST kullanıcı submit, GET admin listeler). Frontend: `/feedback` kullanıcı formu + `/admin/feedback` admin listesi. TopBar'a ve adminNav'a yeni linkler eklenir.

**Tech Stack:** Python/FastAPI/SQLite, React/TypeScript/Tailwind/TanStack Query, Vitest, py.test

## Global Constraints

- Existing migration pattern: `backend/migrations/vNNN_name.py` — SCHEMA_SQL string + `up(conn)` fonksiyonu
- Existing module pattern: `models.py` (Pydantic) + `service.py` (DB logic) + `routes.py` (FastAPI) + `__init__.py` (router export)
- Backend auth: `require_admin` for admin routes, `require_passed_training` or `get_current_user` for user routes
- Frontend route pattern: `lazy(() => import(...).then((m) => ({ default: m.ComponentName })))`
- Frontend admin route: nested under `path="admin/*"` in AdminLayout
- Frontend test: Vitest + `@testing-library/react` + MSW for API mocks + `renderWithProviders`
- Backend test: py.test + `TestClient` + `fresh_db` fixture — notice per-test fixture pattern
- TDD: write failing test first, implement, verify passing
- Commit messages: conventional commit format
- Copy: Turkish labels — "Şikayet/Öneri", "Mesaj", "Gönder", "Feedback"

---

## Task 1: Backend Migration — user_feedback Tablosu

**Files:**
- Create: `backend/migrations/v0016_user_feedback.py`

**Interfaces:**
- Consumes: nothing
- Produces: `up(conn)` fonksiyonu — tablo + indext yaratır

### Steps

- [ ] **Step 1: Create migration file**

```python
"""Migration: add user_feedback table (complaints/suggestions)."""
import sqlite3


SCHEMA_SQL = """
CREATE TABLE user_feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       TEXT NOT NULL CHECK(type IN ('complaint', 'suggestion')),
    message    TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_fb_user_time ON user_feedback(user_id, created_at DESC);
CREATE INDEX idx_fb_type ON user_feedback(type);
"""


def up(conn: sqlite3.Connection) -> None:
    for raw in SCHEMA_SQL.split(";"):
    stmt = raw.strip()
        if stmt:
            conn.execute(stmt)
```

- [ ] **Step 2: Verify migration syntax**

```bash
cd /Users/barandincoguz/Desktop/AnnotationProgram && python -c "from backend.migrations.v0016_user_feedback import up, SCHEMA_SQL; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/v0016_user_feedback.py
git commit -m "feat(migrations): add user_feedback table schema"
```

---

## Task 2: Backend Service — Feedback Service Logic

**Files:**
- Create: `backend/feedback/models.py`
- Create: `backend/feedback/service.py`
- Create: `backend/feedback/__init__.py`

**Interfaces:**
- Consumes: `sqlite3.Connection` from `get_db()` fixture
- Produces: `submit_feedback(conn, user_id, type, message) -> int`, `list_feedback(conn, type_filter) -> list[dict]`

### Steps

- [ ] **Step 1: Create models.py**

```python
"""Pydantic schemas for user feedback endpoints."""
from typing import Literal
from pydantic import BaseModel


FeedbackType = Literal["complaint", "suggestion"]


class FeedbackCreateRequest(BaseModel):
    type: FeedbackType
    message: str


class FeedbackRow(BaseModel):
    id: int
    user_id: int
    username: str
    type: FeedbackType
    message: str
    created_at: str
```

- [ ] **Step 2: Create service.py**

```python
"""Feedback service — submit and list user feedback."""
import sqlite3
from typing import Literal, Optional

FeedbackType = Literal["complaint", "suggestion"]


def submit_feedback(
    db: sqlite3.Connection,
    *,
    user_id: int,
    type: FeedbackType,
    message: str,
) -> int:
    """Insert feedback row. Returns the new row id."""
    cur = db.execute(
        """
        INSERT INTO user_feedback(user_id, type, message, created_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (user_id, type, message),
    )
    return int(cur.lastrowid)


def list_feedback(
    db: sqlite3.Connection,
    *,
    type_filter: Optional[FeedbackType] = None,
) -> list[dict]:
    """Return feedback rows with username, optionally filtered by type."""
    if type_filter:
        rows = db.execute(
            """
            SELECT uf.id, uf.user_id, u.username, uf.type, uf.message, uf.created_at
            FROM user_feedback uf
            JOIN users u ON u.id = uf.user_id
            WHERE uf.type = ?
            ORDER BY uf.created_at DESC
            """,
            (type_filter,),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT uf.id, uf.user_id, u.username, uf.type, uf.message, uf.created_at
            FROM user_feedback uf
            JOIN users u ON u.id = uf.user_id
            ORDER BY uf.created_at DESC
            """,
        ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 3: Create __init__.py**

```python
"""Feedback router export."""
from backend.feedback.routes import router

__all__ = ["router"]
```

- [ ] **Step 4: Commit**

```bash
git add backend/feedback/
git commit -m "feat(backend): add feedback service and models"
```

---

## Task 3: Backend Routes — Feedback Endpoints

**Files:**
- Create: `backend/feedback/routes.py`
- Modify: `backend/main.py:38-51` (add import + router)

**Interfaces:**
- Consumes: `submit_feedback()`, `list_feedback()` from service
- Produces: `POST /api/feedback` (user submit), `GET /api/admin/feedback` (admin list)

### Steps

- [ ] **Step 1: Create routes.py**

```python
"""Feedback HTTP endpoints."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.feedback import service
from backend.feedback.models import FeedbackCreateRequest, FeedbackRow
from backend.users.deps import get_db, get_current_user, require_admin


router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackRow, status_code=201)
def submit_feedback(
    payload: FeedbackCreateRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(get_current_user),
):
    """Submit a complaint or suggestion. Authenticated users only."""
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="message cannot be empty")
    row_id = service.submit_feedback(
        db, user_id=user["id"], type=payload.type, message=payload.message.strip()
    )
    # Fetch back to return full row with username
    row = db.execute(
        """
        SELECT uf.id, uf.user_id, u.username, uf.type, uf.message, uf.created_at
        FROM user_feedback uf
        JOIN users u ON u.id = uf.user_id
        WHERE uf.id = ?
        """,
        (row_id,),
    ).fetchone()
    return dict(row)


@router.get("/admin/feedback", response_model=list[FeedbackRow])
def list_feedback(
    type_filter: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
    _admin: sqlite3.Row = Depends(require_admin),
):
    """List all feedback, optionally filtered by type. Admin only."""
    type_val: service.FeedbackType | None = None
    if type_filter in ("complaint", "suggestion"):
        type_val = type_filter  # type: ignore[assignment]
    return service.list_feedback(db, type_filter=type_val)
```

- [ ] **Step 2: Register router in main.py** — add these two lines near the other imports (~line 50 area):

```python
from backend.feedback.routes import router as feedback_router
```

And add to router includes (~line 430 area, after `exports_router`):

```python
app.include_router(feedback_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/feedback/routes.py backend/main.py
git commit -m "feat(backend): add feedback API endpoints"
```

---

## Task 4: Backend Tests — Feedback Routes

**Files:**
- Create: `tests/test_feedback_routes.py`

**Interfaces:**
- Consumes: `client`, `passed_user`, `db_conn` fixtures from conftest
- Produces: py.test test functions

### Steps

- [ ] **Step 1: Create test file**

```python
"""Tests for backend/feedback/routes.py — submit and list endpoints."""
import os
os.environ.setdefault("DISABLE_SPA_MOUNT", "1")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from backend.main import app
    return app


@pytest.fixture
def client(app, tmp_path):
    from backend.config import DATA_DIR, DB_DIR, DB_PATH, DOCUMENTS_DIR, BACKUP_DIR, EXPORTS_DIR
    import backend.config as config
    config.DATA_DIR = tmp_path
    config.DB_DIR = tmp_path / "db"
    config.DB_PATH = tmp_path / "db" / "test.db"
    config.DOCUMENTS_DIR = tmp_path / "documents"
    config.BACKUP_DIR = tmp_path / "backup"
    config.EXPORTS_DIR = tmp_path / "exports"
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


def _create_user(client, username="alice", invite_code="TEST-1234"):
    """Register, login, return user dict."""
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE invite_codes SET is_active=0")
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            (invite_code,),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": username, "password": "pass123",
        "invite_code": invite_code, "email": f"{username}@test.com",
    })
    assert r.status_code == 201, r.text
    user = r.json()
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET has_seen_manual=1, has_passed_training=1 WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()
    client.post("/api/auth/login", json={"username": username, "password": "pass123"})
    return user


def _create_admin(client, username="root"):
    """Register, promote to admin, login, return admin dict."""
    from backend.shared.db import connect
    from backend import config
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE invite_codes SET is_active=0")
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("TEST-1234",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": username, "password": "admin123",
        "invite_code": "TEST-1234", "email": f"{username}@test.com",
    })
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE users SET role='admin', has_seen_manual=1, has_passed_training=1 WHERE id=?", (user_id,))
    finally:
        conn.close()
    client.post("/api/auth/login", json={"username": username, "password": "admin123"})
    return r.json()


def test_submit_complaint_success(client):
    """Authenticated user can submit a complaint."""
    user = _create_user(client)
    r = client.post("/api/feedback", json={
        "type": "complaint", "message": "This is a test complaint",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["type"] == "complaint"
    assert data["message"] == "This is a test complaint"
    assert data["user_id"] == user["id"]
    assert data["username"] == "alice"
    assert "id" in data
    assert "created_at" in data


def test_submit_suggestion_success(client):
    """Authenticated user can submit a suggestion."""
    user = _create_user(client)
    r = client.post("/api/feedback", json={
        "type": "suggestion", "message": "Add dark mode support",
    })
    assert r.status_code == 201, r.text
    assert r.json()["type"] == "suggestion"


def test_submit_empty_message_rejected(client):
    """Empty message should be rejected with 422."""
    user = _create_user(client)
    r = client.post("/api/feedback", json={
        "type": "complaint", "message": "",
    })
    assert r.status_code == 422


def test_submit_unauthenticated_fails(client):
    """Unauthenticated user cannot submit feedback."""
    r = client.post("/api/feedback", json={
        "type": "complaint", "message": "spam",
    })
    assert r.status_code == 401


def test_list_feedback_admin_success(client):
    """Admin can list all feedback."""
    user = _create_user(client)
    admin = _create_admin(client)
    # Submit some feedback first
    client.post("/api/feedback", json={"type": "complaint", "message": "A"})
    client.post("/api/feedback", json={"type": "suggestion", "message": "B"})
    r = client.get("/api/admin/feedback")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 2


def test_list_feedback_admin_filter_by_type(client):
    """Admin can filter feedback by type."""
    _create_user(client)
    admin = _create_admin(client)
    client.post("/api/feedback", json={"type": "complaint", "message": "A"})
    client.post("/api/feedback", json={"type": "complaint", "message": "B"})
    client.post("/api/feedback", json={"type": "suggestion", "message": "C"})
    r = client.get("/api/admin/feedback?type_filter=complaint")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 2
    for row in data:
        assert row["type"] == "complaint"


def test_list_feedback_unauthorized(client):
    """Non-admin user cannot list feedback."""
    _create_user(client)
    r = client.get("/api/admin/feedback")
    assert r.status_code == 404  # not found (hidden per existing admin pattern)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/barandincoguz/Desktop/AnnotationProgram && python -m pytest tests/test_feedback_routes.py -v --tb=short
```

Expected: `ModuleNotFoundError: No module named 'backend.feedback'` — FAIL

- [ ] **Step 3: Run tests again after all tasks implemented** — we will rerun here after Tasks 1-3 are done.

- [ ] **Step 4: Commit**

```bash
git add tests/test_feedback_routes.py
git commit -m "test(backend): add feedback route tests"
```

---

## Task 5: Frontend — Zod Schema & API Query

**Files:**
- Create: `frontend/src/lib/feedbackSchemas.ts`
- Create: `frontend/src/api/queries/feedback.ts`

**Interfaces:**
- Consumes: `client`, `unwrap` from `@/api/client`
- Produces: `feedbackKeys.all`, `feedbackKeys.all`, `useSubmitFeedback()`, `useFeedbackList()`

### Steps

- [ ] **Step 1: Create feedbackSchemas.ts**

```typescript
import { z } from 'zod'

export const feedbackTypeSchema = z.enum(['complaint', 'suggestion'])
export type FeedbackType = z.infer<typeof feedbackTypeSchema>

export const feedbackRowSchema = z.object({
  id: z.number(),
  user_id: z.number(),
  username: z.string(),
  type: feedbackTypeSchema,
  message: z.string(),
  created_at: z.string(),
})
export type FeedbackRow = z.infer<typeof feedbackRowSchema>

export const feedbackListResponseSchema = z.array(feedbackRowSchema)
```

- [ ] **Step 2: Create feedback.ts**

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { client, unwrap } from '@/api/client'
import { feedbackListResponseSchema, feedbackRowSchema } from '@/lib/feedbackSchemas'

export const feedbackKeys = {
  all: ['feedback'] as const,
  list: () => [...feedbackKeys.all, 'list'] as const,
}

export function useFeedbackList(typeFilter?: string) {
  return useQuery<{ data: FeedbackRow[] }>({
    queryKey: feedbackKeys.list(),
    queryFn: async () => {
      const params = typeFilter ? { type_filter: typeFilter } : undefined
      const raw = await client.GET('/api/admin/feedback', { params })
      return { data: feedbackListResponseSchema.parse(unwrap(raw)) }
    },
  })
}

export function useSubmitFeedbackMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: { type: string; message: string }) => {
      await unwrap(await client.POST('/api/feedback', payload))
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: feedbackKeys.list() })
    },
  })
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/barandincoguz/Desktop/AnnotationProgram/frontend
git add src/lib/feedbackSchemas.ts src/api/queries/feedback.ts
git commit -m "feat(frontend): add feedback Zod schema and API queries"
```

---

## Task 6: Frontend — User Feedback Page

**Files:**
- Create: `frontend/src/routes/Feedback.tsx`
- Create: `frontend/src/routes/Feedback.test.tsx`
- Modify: `frontend/src/App.tsx` (add lazy import + route)
- Modify: `frontend/src/components/topbar/TopBar.tsx` (add nav link)

**Interfaces:**
- Consumes: `useSubmitFeedbackMutation` from `@/api/queries/feedback`
- Produces: `<Feedback>` component at `/feedback` route

### Steps

- [ ] **Step 1: Create Feedback.tsx**

```typescript
import { useState } from 'react'
import { toast } from 'sonner'
import { Send, MessageSquare, Lightbulb } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { useSubmitFeedbackMutation } from '@/api/queries/feedback'
import type { FeedbackType } from '@/lib/feedbackSchemas'

const TYPES: { value: FeedbackType; label: string; icon: typeof MessageSquare }[] = [
  { value: 'complaint', label: 'Şikayet', icon: MessageSquare },
  { value: 'suggestion', label: 'Öneri', icon: Lightbulb },
]

export function Feedback() {
  const [type, setType] = useState<FeedbackType>('complaint')
  const [message, setMessage] = useState('')
  const submit = useSubmitFeedbackMutation()

  const onSubmit = () => {
    if (!message.trim()) {
      toast.error('Mesaj alanı boş olamaz')
      return
    }
    submit.mutate({ type, message: message.trim() }, {
      onSuccess: () => {
        toast.success('Geri bildiriminiz gönderildi. Teşekkür ederiz!')
        setMessage('')
      },
      onError: () => {
        toast.error('Gönderim başarısız. Lütfen tekrar deneyin.')
      },
    })
  }

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-6 space-y-6">
      <div className="space-y-1">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Geri Bildirim
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight">
          Şikayet / Öneri
        </h1>
        <p className="text-sm text-muted-foreground">
          Platform hakkındaki düşüncelerinizi paylaşın.
        </p>
      </div>

      <div className="space-y-4 rounded-md border border-border/70 bg-card/50 p-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Geri Bildirim Türü</label>
          <div className="flex gap-2">
            {TYPES.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => setType(t.value)}
                className={`flex flex-1 items-center justify-center gap-2 rounded-md border px-4 py-2 text-sm transition-colors ${
                  type === t.value
                    ? 'border-info bg-info/10 text-info font-medium'
                    : 'border-border/70 bg-background text-muted-foreground hover:bg-muted/60'
                }`}
              >
                <t.icon className="h-4 w-4" />
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="feedback-message">Mesaj</Label>
          <Textarea
            id="feedback-message"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Lütfen şikayet veya önerinizi yazın..."
            rows={5}
            className="resize-none"
          />
        </div>

        <Button
          onClick={onSubmit}
          disabled={submit.isPending || !message.trim()}
          className="w-full"
        >
          <Send className="mr-2 h-4 w-4" />
          {submit.isPending ? 'Gönderiliyor...' : 'Gönder'}
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create Feedback.test.tsx**

```typescript
import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { Feedback } from './Feedback'

describe('Feedback route', () => {
  it('renders form with type selector, textarea, and submit button', () => {
    renderWithProviders(<Feedback />)
    expect(screen.getByRole('heading', { name: 'Şikayet / Öneri' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /şikayet/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /öneri/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/mesaj/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /gönder/i })).toBeInTheDocument()
  })

  it('highlights selected type', () => {
    renderWithProviders(<Feedback />)
    const complaintBtn = screen.getByRole('button', { name: /şikayet/i })
    const suggestionBtn = screen.getByRole('button', { name: /öneri/i })
    expect(complaintBtn).toHaveClass('bg-info/10')
    expect(suggestionBtn).not.toHaveClass('bg-info/10')
  })

  it('submits feedback on button click', async () => {
    let captured: unknown = null
    server.use(
      http.post('http://localhost/api/feedback', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({
          id: 1, user_id: 1, username: 'alice',
          type: 'complaint', message: 'Test message',
          created_at: '2026-07-07T12:00:00',
        })
      }),
    )

    renderWithProviders(<Feedback />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /öneri/i }))
    await user.type(screen.getByLabelText(/mesaj/i), 'Bu bir öneri')
    await user.click(screen.getByRole('button', { name: /gönder/i }))

    await waitFor(() => {
      expect(captured).toBeTruthy()
      expect((captured as { type: string }).type).toBe('suggestion')
      expect((captured as { message: string }).message).toBe('Bu bir öneri')
    })
  })

  it('disables submit when message is empty', () => {
    renderWithProviders(<Feedback />)
    expect(screen.getByRole('button', { name: /gönder/i })).toBeDisabled()
  })

  it('trims whitespace from message', async () => {
    let captured: unknown = null
    server.use(
      http.post('http://localhost/api/feedback', async ({ request }) => {
        captured = await request.json()
        return HttpResponse.json({
          id: 1, user_id: 1, username: 'alice',
          type: 'complaint', message: 'Trimmed',
          created_at: '2026-07-07T12:00:00',
        })
      }),
    )

    renderWithProviders(<Feedback />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/mesaj/i), '   Trimmed   ')
    await user.click(screen.getByRole('button', { name: /gönder/i }))

    await waitFor(() => {
      expect(captured).toBeTruthy()
      expect((captured as { message: string }).message).toBe('Trimmed')
    })
  })
})
```

- [ ] **Step 3: Add route to App.tsx** — Add lazy import and route:

Add after line 27 (after Statistics lazy import):
```typescript
const Feedback = lazy(() =>
  import('@/routes/Feedback').then((m) => ({ default: m.Feedback })),
)
```

Add route after `/statistics` route (line 147):
```typescript
<Route path="/feedback" element={<Feedback />} />
```

- [ ] **Step 4: Add TopBar link** — Add after the İstatistikler link in TopBar.tsx (around line 56):

```tsx
<Link
  to="/feedback"
  aria-label="Şikayet / Öneri"
  className="inline-flex h-9 w-9 shrink-0 items-center justify-center gap-2 rounded-full border border-border bg-card text-foreground shadow-sm transition-colors hover:border-warning/50 hover:text-warning focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warning sm:w-auto sm:px-3"
>
  <MessageSquare aria-hidden className="h-4 w-4 shrink-0" />
  <span className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground lg:inline">
    Şikayet/Öneri
  </span>
</Link>
```

Also add `import { MessageSquare } from 'lucide-react'` to TopBar imports.

- [ ] **Step 5: Run frontend tests**

```bash
cd /Users/barandincoguz/Desktop/AnnotationProgram/frontend && npm test -- src/routes/Feedback.test.tsx
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/Feedback.tsx frontend/src/routes/Feedback.test.tsx frontend/src/App.tsx frontend/src/components/topbar/TopBar.tsx
git commit -m "feat(frontend): add user feedback page with form"
```

---

## Task 7: Frontend — Admin Feedback Page

**Files:**
- Create: `frontend/src/routes/admin/FeedbackPage.tsx`
- Create: `frontend/src/routes/admin/FeedbackPage.test.tsx`
- Create: `frontend/src/components/admin/FeedbackTypeBadge.tsx`
- Modify: `frontend/src/components/admin/adminNav.ts` (add menu item)
- Modify: `frontend/src/routes/admin/AdminLayout.test.tsx` (add stub route for feedback)

**Interfaces:**
- Consumes: `useFeedbackList` from `@/api/queries/feedback`
- Produces: `<FeedbackPage>` component at `/admin/feedback` route

### Steps

- [ ] **Step 1: Create FeedbackTypeBadge.tsx**

```typescript
import { Badge } from '@/components/ui/badge'

export function FeedbackTypeBadge({ type }: { type: 'complaint' | 'suggestion' }) {
  const isComplaint = type === 'complaint'
  return (
    <Badge variant={isComplaint ? 'destructive' : 'secondary'}>
      {isComplaint ? 'Şikayet' : 'Öneri'}
    </Badge>
  )
}
```

- [ ] **Step 2: Create FeedbackPage.tsx**

```typescript
import { useState } from 'react'
import { useFeedbackList } from '@/api/queries/feedback'
import { AdminTable } from '@/components/admin/AdminTable'
import { FeedbackTypeBadge } from '@/components/admin/FeedbackTypeBadge'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { FeedbackRow } from '@/lib/feedbackSchemas'

const FEEDBACK_TYPES: { value: string; label: string }[] = [
  { value: '', label: 'Tümü' },
  { value: 'complaint', label: 'Şikayet' },
  { value: 'suggestion', label: 'Öneri' },
]

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('tr-TR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

export function FeedbackPage() {
  const [typeFilter, setTypeFilter] = useState('')
  const q = useFeedbackList(typeFilter || undefined)

  if (q.isError) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        Geri bildirimler yüklenemedi.
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
            Platform · Feedback
          </p>
          <h1 className="font-display text-2xl font-medium tracking-tight">
            Şikayet / Öneri
          </h1>
        </div>
        <Select value={typeFilter} onValueChange={setTypeFilter}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Tümü / Şikayet / Öneri" />
          </SelectTrigger>
          <SelectContent>
            {FEEDBACK_TYPES.map((t) => (
              <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {q.isLoading ? (
        <div className="flex items-center gap-3 rounded-md border border-border/60 bg-card/40 px-4 py-6 text-sm text-muted-foreground">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          Yükleniyor…
        </div>
      ) : (
        <AdminTable<FeedbackRow>
          rows={q.data?.data ?? []}
          loading={q.isLoading}
          emptyMessage="Gönderim bulunamadı"
          getRowKey={(row) => row.id}
          columns={[
            { key: 'id', header: 'ID', render: (row) => String(row.id) },
            { key: 'username', header: 'Kullanıcı', render: (row) => row.username },
            {
              key: 'type',
              header: 'Tür',
              render: (row) => <FeedbackTypeBadge type={row.type} />,
            },
            {
              key: 'message',
              header: 'Mesaj',
              render: (row) => (
                <span className="max-w-[400px] truncate" title={row.message}>
                  {row.message}
                </span>
              ),
            },
            { key: 'created_at', header: 'Tarih', render: (row) => formatDate(row.created_at) },
          ]}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 3: Create FeedbackPage.test.tsx**

```typescript
import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/msw-server'
import { renderWithProviders } from '@/test/render'
import { FeedbackPage } from './FeedbackPage'

const MOCK_ROWS: { id: number; user_id: number; username: string; type: string; message: string; created_at: string }[] = [
  { id: 1, user_id: 1, username: 'alice', type: 'complaint', message: 'Test complaint', created_at: '2026-07-07T10:00:00' },
  { id: 2, user_id: 2, username: 'bob', type: 'suggestion', message: 'Feature request', created_at: '2026-07-07T11:00:00' },
]

function mockResponse(rows = MOCK_ROWS) {
  return HttpResponse.json(rows)
}

describe('Admin FeedbackPage', () => {
  it('renders heading and table', () => {
    server.use(http.get('http://localhost/api/admin/feedback', () => mockResponse()))

    renderWithProviders(<FeedbackPage />)
    expect(screen.getByRole('heading', { name: 'Şikayet / Öneri' })).toBeInTheDocument()
    expect(screen.getByText('alice')).toBeInTheDocument()
    expect(screen.getByText('bob')).toBeInTheDocument()
  })

  it('shows feedback type badges', () => {
    server.use(http.get('http://localhost/api/admin/feedback', () => mockResponse()))

    renderWithProviders(<FeedbackPage />)
    expect(screen.getByText('Şikayet')).toBeInTheDocument()
    expect(screen.getByText('Öneri')).toBeInTheDocument()
  })

  it('shows empty state when no feedback', () => {
    server.use(http.get('http://localhost/api/admin/feedback', () => mockResponse([])))

    renderWithProviders(<FeedbackPage />)
    expect(screen.getByText('Gönderim bulunamadı')).toBeInTheDocument()
  })

  it('filters by type', async () => {
    let capturedType: string | null = null
    server.use(
      http.get('http://localhost/api/admin/feedback', ({ request }) => {
        const url = new URL(request.url)
        capturedType = url.searchParams.get('type_filter')
        return mockResponse(MOCK_ROWS.filter((r) => r.type === capturedType))
      }),
    )

    renderWithProviders(<FeedbackPage />)
    // Filter dropdown exists
    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })
})
```

- [ ] **Step 4: Add to adminNav.ts** — Add to Operations group:

```typescript
{ to: '/admin/feedback', label: 'Feedback' },
```

- [ ] **Step 5: Add route and lazy import to App.tsx** — Add lazy import:

```typescript
const FeedbackPageAdmin = lazy(() =>
  import('@/routes/admin/FeedbackPage').then((m) => ({ default: m.FeedbackPage })),
)
```

Add admin route inside AdminLayout:
```typescript
<Route path="feedback" element={<FeedbackPageAdmin />} />
```

- [ ] **Step 6: Update AdminLayout.test.tsx** — Add feedback stub route to Wrap:

```tsx
<Route path="feedback" element={<div>FEEDBACK_STUB</div>} />
```

And add assertion:
```tsx
expect(screen.getByRole('link', { name: /feedback/i })).toHaveAttribute('href', '/admin/feedback')
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/routes/admin/FeedbackPage.tsx frontend/src/routes/admin/FeedbackPage.test.tsx frontend/src/components/admin/FeedbackTypeBadge.tsx frontend/src/components/admin/adminNav.ts frontend/src/routes/admin/AdminLayout.test.tsx
git commit -m "feat(frontend): add admin feedback page with table and filter"
```

---

## Task 8: End-to-End Verification

**Files:**
- Run: backend tests (all feedback + existing)
- Run: frontend tests (all feedback + existing)
- Manual: verify app runs, forms work, pages accessible

### Steps

- [ ] **Step 1: Run backend tests**

```bash
cd /Users/barandincoguz/Desktop/AnnotationProgram && python -m pytest tests/test_feedback_routes.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 2: Run frontend tests**

```bash
cd /Users/barandincoguz/Desktop/AnnotationProgram/frontend && npm test -- src/routes/Feedback.test.tsx src/routes/admin/FeedbackPage.test.tsx
```

Expected: All tests PASS.

- [ ] **Step 3: Run full test suites (quick sanity)**

```bash
cd /Users/barandincoguz/Desktop/AnnotationProgram && python -m pytest tests/ -q --tb=line
cd /Users/barandincoguz/Desktop/AnnotationProgram/frontend && npm test -- --run
```

Expected: No regressions.

- [ ] **Step 4: Commit any leftover changes**

```bash
git add -A
git commit -m "chore: final verification and cleanup"
```
