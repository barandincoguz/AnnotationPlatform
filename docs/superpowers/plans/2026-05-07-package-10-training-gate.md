# Paket 10 — Training Gate (Quiz + Gold-Doc Annotation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the bursiyer onboarding training gate — a 5-question multiple-choice quiz + a 3-gold-doc annotation challenge with subset-semantic concept matching. Users get up to 3 attempts. On pass, `users.has_passed_training=1`, +50 XP via gamification, and a notification is created. Built-in placeholder gold docs ship with the code; admins (Paket 11) and the new CLI command override or extend them.

**Architecture:** New `backend/training/` module with: a static placeholder `quiz_data.py` (8-10 Turkish questions about annotation rules), a static placeholder `gold_docs.py` (3 minimal sample gold docs), a hybrid resolver that merges code baseline with `training_gold_doc_overrides` rows from the DB (per-spec §"Q5 hibrit modeli"), pure scoring functions for quiz + concept matching, an attempt-state service, and three HTTP endpoints (`GET /api/training/start`, `POST /api/training/quiz/submit`, `POST /api/training/annotate/submit`). Auth gate is `require_seen_manual` (NOT `require_passed_training` — the user is taking training right now). The endpoint flow is **deterministic-by-attempt-id**: starting an attempt creates a `training_attempts` row whose `id` becomes the seed for `random.Random(attempt_id)` selection of 5 questions and 3 gold docs — server holds no per-attempt session state. A new CLI subcommand imports the user's real gold docs from a JSON file into `training_gold_doc_overrides` (so today's placeholder data is swapped without code changes).

**Tech Stack:** Existing FastAPI + SQLite + Pydantic. New: `random.Random(seed)` for deterministic selection. No new third-party deps. Reuses `backend.gamification.service.award_xp`, `backend.notifications.service.create`, `backend.shared.audit`, `backend.shared.settings`, `backend.users.deps.require_seen_manual`.

---

## Mimari Kararlar (Locked)

- **Module layout:**
  - `backend/training/quiz_data.py` — static `QUIZ_QUESTIONS` list (8-10 Turkish questions; admin can override via Paket 11).
  - `backend/training/gold_docs.py` — static `GOLD_DOCS` baseline list (3 minimal placeholder docs; user's real ones come via CLI overrides).
  - `backend/training/matching.py` — pure functions: `score_quiz`, `match_gold_doc`, `is_doc_pass`. No DB.
  - `backend/training/service.py` — `start_attempt`, `submit_quiz`, `submit_annotation`, `finalize_if_complete`, `get_active_gold_docs` (hybrid resolver per spec lines 1007-1034), lockout checks. DB writes live here.
  - `backend/training/models.py` — Pydantic schemas for the 3 endpoints.
  - `backend/training/routes.py` — 3 HTTP endpoints; auth: `require_seen_manual`.
  - `backend/cli.py` — extended with `import-gold-docs <path>` subcommand.
- **Auth:** All training endpoints use `require_seen_manual` (NOT `require_passed_training` — that would be circular). Already-passed users get 409 from `/api/training/start` (spec: training pass is permanent, can't retake).
- **Lockout:** If `training_attempts` count for user >= `training.max_attempts` (default 3) AND no row has `passed=1`, `/api/training/start` returns 403 with `{"error": "max_attempts_reached"}`. Admin reset (Paket 11) deletes all attempts for the user; that's how lockout is cleared.
- **Attempt state model:**
  - `start_attempt` INSERTs a `training_attempts` row with `quiz_score=0, quiz_total=5, annotation_pass_count=0, annotation_total=3, passed=0, finished_at=started_at` (placeholder until finalize).
  - The `id` of this row IS the attempt_id and the deterministic seed.
  - `random.Random(attempt_id).sample(QUIZ_QUESTIONS, 5)` and same for gold docs — server can re-derive selection on every submit without storing it.
  - `submit_quiz` updates `quiz_score`. Idempotency: if `quiz_score` is already non-zero (i.e. already submitted) → 409.
  - `submit_annotation` appends to `annotation_details_json` (a dict keyed by `gold_id`). 409 if same `gold_id` re-submitted.
  - **Finalize trigger**: when the 3rd distinct `gold_id` lands in `annotation_details_json`, the orchestrator computes the final pass and updates `users.has_passed_training`, awards XP, persists notification.
- **Quiz scoring:** Each correct answer = 1 point. `quiz_pass_threshold` (default 4) compared with `>=`.
- **Subset-semantic gold-doc matching:**
  - A user reference `r` matches a gold concept `g` iff: for every key `k` in `g`, `g[k] != ""` and `r.get(k) == g[k]`. Empty/missing values in `g` are wildcards. `source_text` is **never** consulted in matching — even if present in `g`, it is ignored. (`source_text` IS still required in the user's submitted reference per the existing annotations contract — but it doesn't influence training score.)
  - Per gold doc: count distinct `g` concepts that have at least one matching `r`. Pass iff `match_count >= min_concept_count`.
  - Doc pass annotated in `annotation_details_json[gold_id] = {passed: bool, matched_concepts: [...], expected: N, hit: M}`.
  - Aggregate: `annotation_pass_count` = sum of `passed=True` across the 3 docs.
- **Final pass criteria** (atomic in `finalize_if_complete`):
  - `quiz_score >= training.quiz_pass_threshold` (default 4)
  - AND `annotation_pass_count >= training.annotation_pass_threshold` (default 2)
  - On pass: `UPDATE users SET has_passed_training=1`, `gamification.award_xp(reason='training_pass', delta=50, related_doc_id=None)`, `notif_service.create(kind='training_passed', title='Tebrikler!', body='Eğitimi başarıyla geçtin. +50 XP kazandın.', data={attempt_id})`, `audit.log_activity(event_type='training_pass')`. Sets `training_attempts.passed=1`, `finished_at=now`.
  - On fail: training_attempts row keeps `passed=0`. No XP, no notification (the failure feedback is in the response body of the final annotate/submit). User can retry up to max_attempts.
- **`xp_training_pass` is one-time:** `award_xp` is called once at finalize. If a user somehow re-passes (shouldn't happen — start endpoint blocks), the ledger row would still write but the `has_passed_training=1` UPDATE is idempotent. Belt-and-suspenders: `start_attempt` rejects already-passed users.
- **Hybrid gold-doc resolver:** Per spec lines 1007-1034:
  ```python
  def get_active_gold_docs(db) -> list[dict]:
      out = []
      seen = set()
      overrides = {row["gold_id"]: row for row in db.execute("SELECT * FROM training_gold_doc_overrides")}
      for code in CODE_BASELINE:
          ov = overrides.get(code["gold_id"])
          if ov and ov["is_deleted"]:
              continue
          if ov:
              out.append({
                  "gold_id": code["gold_id"],
                  "content": ov["content"] or code["content"],
                  "expected_concepts": json.loads(ov["expected_concepts"]) if ov["expected_concepts"] else code["expected_concepts"],
                  "min_concept_count": ov["min_concept_count"] if ov["min_concept_count"] is not None else code["min_concept_count"],
              })
          else:
              out.append(code)
          seen.add(code["gold_id"])
      for ov in overrides.values():
          if ov["source"] == "custom" and not ov["is_deleted"] and ov["gold_id"] not in seen:
              out.append({
                  "gold_id": ov["gold_id"],
                  "content": ov["content"],
                  "expected_concepts": json.loads(ov["expected_concepts"]),
                  "min_concept_count": ov["min_concept_count"],
              })
      return out
  ```
- **Quiz_data is NOT yet hybrid:** The quiz lives in code only for Paket 10. Admin override of quiz questions happens in Paket 11 (out of scope).
- **CLI import format:** The `python -m backend.cli import-gold-docs <path>` reads a JSON file and INSERT-OR-REPLACEs rows into `training_gold_doc_overrides` with `source='custom'`. Format documented in Task 6.
- **Gold doc JSON format (input/output):**
  ```json
  {
    "gold_docs": [
      {
        "gold_id": "gold_real_001",
        "content": "<özelge pdfText>",
        "expected_concepts": [
          {"kanun_no": "5520", "madde": "5"},
          {"kanun_no": "5520", "madde": "5", "fikra": "1", "bent": "a"}
        ],
        "min_concept_count": 1
      }
    ]
  }
  ```
- **`/api/training/start` response shape:** Returns `attempt_id`, full quiz questions (with `id`, `text`, `choices`) — no `correct_choice_idx`! — plus 3 gold docs (with `gold_id`, `content`) — no `expected_concepts` and no `min_concept_count`!
- **Error responses:** Use existing pattern — `HTTPException(status_code=..., detail={"error": "code", "message": "..."})`.
- **No SSE event for training pass — the `notification` event already published by notif_service.create() covers it.** Keeps the SSE event vocabulary tight.
- **Integration with Paket 9:** finalize awards XP through `gamification.award_xp` (NOT through the orchestrator since there's no doc context); creates notification through `notifications.service.create` (which auto-publishes the `notification` SSE event via the gamification orchestrator? — actually no, `notif_service.create` is a pure DB write; SSE publish happens only inside `_publish_unlock_events` in gamification's orchestrator. So training_pass notification is silent on SSE. **Decision: that's fine for Paket 10**; the user is on the training screen and gets the response body directly.) If a future paket wants live SSE for training_pass, add a `publish_to([user_id], "notification", ...)` call at finalize. Out of scope here.
- **Fault isolation at finalize:** Each side-effect (passed-flag flip, XP award, notification create, audit log) wrapped in its own `try/except`. A failure in one shouldn't block the others. The training_attempts row update is the source of truth for "did this attempt pass" — it's the first write and gets done atomically.
- **Type hints on `db`:** Per Paket 7+ reviewer convention, use `db: sqlite3.Connection`.

## Dosya Yapısı

```
backend/training/                       # NEW package
├── __init__.py                         # empty
├── quiz_data.py                        # static QUIZ_QUESTIONS list (8 placeholder TR)
├── gold_docs.py                        # static GOLD_DOCS baseline (3 minimal samples)
├── matching.py                         # score_quiz, match_gold_doc, is_doc_pass (pure)
├── service.py                          # start_attempt, submit_quiz, submit_annotation,
                                        #   finalize_if_complete, get_active_gold_docs
├── models.py                           # Pydantic schemas
└── routes.py                           # 3 endpoints

backend/cli.py                          # MODIFIED: + import-gold-docs subcommand
backend/main.py                         # MODIFIED: mount training_router

tests/test_training_quiz_data.py        # NEW — sanity check on QUIZ_QUESTIONS
tests/test_training_matching.py         # NEW — score_quiz + match_gold_doc + is_doc_pass
tests/test_training_resolver.py         # NEW — get_active_gold_docs hybrid logic
tests/test_training_service.py          # NEW — attempt state transitions, finalize, lockout
tests/test_training_routes.py           # NEW — HTTP integration (start/quiz/annotate)
tests/test_training_pass_integration.py # NEW — end-to-end pass flow + XP + notification
tests/test_cli_import_gold_docs.py      # NEW — CLI subcommand
```

---

## Task 1: Static Quiz Data + Sanity Tests

**Goal:** Ship 8 Turkish placeholder questions about annotation rules. Each has `id`, `text` (question), `choices` (4 options), `correct_choice_idx` (0-3). Plus a sanity test that asserts the shape and the count >= 5 (because we sample 5 per attempt).

**Files:**
- Create: `backend/training/__init__.py`
- Create: `backend/training/quiz_data.py`
- Create: `tests/test_training_quiz_data.py`

- [ ] **Step 1: Create empty package**

Run:
```bash
mkdir -p /Users/barandincoguz/Desktop/deneme/backend/training
touch /Users/barandincoguz/Desktop/deneme/backend/training/__init__.py
```

- [ ] **Step 2: Write `tests/test_training_quiz_data.py`**

```python
"""Sanity check on the static quiz question list.

These tests don't pin specific question content (admin will replace later via
Paket 11) — they pin shape invariants so a future edit doesn't accidentally
break the data model the service code depends on.
"""
from backend.training import quiz_data


def test_questions_present():
    assert len(quiz_data.QUIZ_QUESTIONS) >= 8


def test_at_least_5_questions_for_sampling():
    """The training start endpoint samples 5 random questions per attempt;
    we need a minimum stock of 5 to avoid running out."""
    assert len(quiz_data.QUIZ_QUESTIONS) >= 5


def test_question_shape():
    for q in quiz_data.QUIZ_QUESTIONS:
        assert isinstance(q["id"], str) and q["id"].startswith("q")
        assert isinstance(q["text"], str) and len(q["text"]) >= 10
        assert isinstance(q["choices"], list)
        assert len(q["choices"]) == 4
        assert all(isinstance(c, str) and c for c in q["choices"])
        assert isinstance(q["correct_choice_idx"], int)
        assert 0 <= q["correct_choice_idx"] <= 3


def test_question_ids_unique():
    ids = [q["id"] for q in quiz_data.QUIZ_QUESTIONS]
    assert len(ids) == len(set(ids))


def test_questions_in_turkish():
    """Soft heuristic: at least one Turkish-specific character should appear
    across the question text (ç, ğ, ı, ö, ş, ü). Defends against an English
    placeholder leaking in."""
    text_blob = " ".join(q["text"] for q in quiz_data.QUIZ_QUESTIONS)
    tr_chars = set("çğıöşüÇĞİÖŞÜ")
    assert any(c in text_blob for c in tr_chars)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_training_quiz_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.training.quiz_data'`.

- [ ] **Step 4: Implement `backend/training/quiz_data.py`**

```python
"""Static placeholder quiz questions for the training gate.

Format: each entry has `id`, `text`, `choices` (4 options), `correct_choice_idx`.
Admin override of these questions is out of scope for Paket 10 (planned for
Paket 11). For now, edit this file directly to update question content.

These 8 questions cover the most-needed concepts a bursiyer must know before
annotating real özelge documents:
  - Why source_text is required
  - Reference field semantics (kanun_no vs kanun_ad vs madde vs fikra vs bent)
  - Madde format ("Mükerrer 20", "Geçici 5")
  - is_diff_zero meaning
  - Duplicate-reference rule
  - Lock release timing
  - Skip vs save semantics
  - Empty-references-list legality
"""

QUIZ_QUESTIONS: list[dict] = [
    {
        "id": "q01",
        "text": "Bir referansta source_text alanı zorunludur. Aşağıdakilerden hangisi en doğru gerekçe?",
        "choices": [
            "Frontend'in alanı boş bırakmasını önlemek için.",
            "Sonraki kullanıcıların hangi metin parçasından çıkarıldığını görüp doğrulayabilmesi için.",
            "Veritabanı PRIMARY KEY kısıtlaması zorunlu kılıyor.",
            "Backup sistemi source_text alanına bakarak chunking yapıyor.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q02",
        "text": "Madde alanı için aşağıdaki örneklerden hangisi GEÇERSİZDİR?",
        "choices": [
            "5",
            "Mükerrer 20",
            "Geçici 5",
            "Madde 5'in 1. fıkrasının a bendi",
        ],
        "correct_choice_idx": 3,
    },
    {
        "id": "q03",
        "text": "is_diff_zero=True ne anlama gelir?",
        "choices": [
            "Önceki kullanıcının bıraktığı referans listesi ile şu anki kayıt birebir aynı.",
            "Bu doküman henüz hiç anotasyonlanmamış.",
            "Kayıt sırasında bir hata oldu, hiçbir referans yazılmadı.",
            "Kullanıcı 'Atla' butonuna bastı.",
        ],
        "correct_choice_idx": 0,
    },
    {
        "id": "q04",
        "text": "Aynı dokümana aynı 6'lı tuple (kanun_no, kanun_ad, madde, fikra, bent, source_text) ile iki kez referans eklenirse ne olur?",
        "choices": [
            "İkincisi sessizce yok sayılır.",
            "Sistem 422 ile DuplicateReference hatası döndürür.",
            "Ledger'a iki ayrı satır olarak yazılır.",
            "İlk olan otomatik silinir.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q05",
        "text": "Bir özelge dokümanında hiçbir kanun atfı yoksa ne yapılmalı?",
        "choices": [
            "Doküman 'Atla' ile geçilmeli.",
            "Boş bir referans listesi ([]) ile 'Sakla' edilmelidir — bu meşru bir durumdur.",
            "Sahte bir referans ekleyip kaydedilmelidir.",
            "Admin'e bildirim gönderilmelidir.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q06",
        "text": "kanun_no ve kanun_ad birlikte verilirken hangi durum tipiktir?",
        "choices": [
            "kanun_no zorunlu, kanun_ad opsiyonel ama her ikisi de tutarlı olmalı (örn. 5520 → 'Kurumlar Vergisi Kanunu').",
            "Sadece kanun_ad yeterlidir; kanun_no opsiyonel.",
            "İkisi de zorunludur, eksik olursa 422 döner.",
            "İkisi de opsiyoneldir, source_text yeterlidir.",
        ],
        "correct_choice_idx": 0,
    },
    {
        "id": "q07",
        "text": "Bir doküman üzerinde 'Sakla' işlemi başarıyla tamamlandığında, kullanıcının dokümanı üzerindeki kilidiyle (lock) ne olur?",
        "choices": [
            "Kilit 5 dakika daha uzatılır.",
            "Kilit otomatik olarak serbest bırakılır.",
            "Kilit, kullanıcı 'Çıkış' yapana kadar kalır.",
            "Kilit yalnızca admin tarafından kaldırılabilir.",
        ],
        "correct_choice_idx": 1,
    },
    {
        "id": "q08",
        "text": "Aynı dokümanı iki bursiyer aynı anda anotasyonlamaya çalışırsa ne olur?",
        "choices": [
            "İkisi de aynı anda yazabilir, son kaydedenin verisi geçerli olur.",
            "İkincisi 409 Conflict alır ve modal ile 'Başka doc seç' yönlendirmesi yapılır.",
            "Sistem otomatik olarak ikincinin oturumunu kapatır.",
            "İkisinden hangisi 'Sakla'ya önce basarsa onun girişi yazılır, diğerininki sessizce kaybolur.",
        ],
        "correct_choice_idx": 1,
    },
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_training_quiz_data.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 398 prior + 5 new = 403 PASS.

- [ ] **Step 7: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/training/__init__.py backend/training/quiz_data.py tests/test_training_quiz_data.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(training): add 8 placeholder Turkish quiz questions

Static module with 8 multiple-choice questions covering source_text,
field semantics, madde format, is_diff_zero, duplicate handling, empty
refs, kanun_no/kanun_ad pairing, and lock release after save. Sanity
tests pin shape invariants without locking specific content.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Static Gold Docs Baseline + Resolver Tests

**Goal:** Ship 3 minimal placeholder gold docs in `backend/training/gold_docs.py` (clearly marked as samples). The user's real 5-6 docs will be loaded via the CLI subcommand in Task 6 as DB overrides.

**Files:**
- Create: `backend/training/gold_docs.py`

- [ ] **Step 1: Implement `backend/training/gold_docs.py`**

```python
"""Code-baseline gold-doc list for the training annotation challenge.

These 3 entries are PLACEHOLDER samples shipped with the codebase. The
expected production gold set will be loaded via the CLI subcommand
`python -m backend.cli import-gold-docs <path>` as overrides in the
`training_gold_doc_overrides` table — see backend/cli.py and the hybrid
resolver in `backend.training.service.get_active_gold_docs`.

Format:
  gold_id            — stable identifier (used by overrides table)
  content            — full özelge text the user reads while annotating
  expected_concepts  — list of partial-tuple dicts; subset semantics:
                       a user reference matches a concept iff every
                       non-empty key in the concept is identically
                       present in the user's reference. source_text
                       is never compared.
  min_concept_count  — minimum number of concepts the user must hit
                       to pass this gold doc.
"""

GOLD_DOCS: list[dict] = [
    {
        "gold_id": "sample_kvk_5",
        "content": (
            "Mükellef, Kurumlar Vergisi Kanunu'nun 5'inci maddesinin 1. fıkrasının (a) bendi "
            "uyarınca iştirak kazançları istisnasından faydalanıp faydalanamayacağını sormaktadır. "
            "Anılan madde hükmüne göre, tam mükellefiyete tabi başka bir kurumun sermayesine "
            "katılım nedeniyle elde edilen kâr payları kurumlar vergisinden müstesnadır."
        ),
        "expected_concepts": [
            {"kanun_no": "5520", "madde": "5"},
            {"kanun_no": "5520", "madde": "5", "fikra": "1", "bent": "a"},
        ],
        "min_concept_count": 1,
    },
    {
        "gold_id": "sample_kdv_29",
        "content": (
            "Mükellef tarafından yapılan ihracat işlemine ilişkin olarak Katma Değer Vergisi "
            "Kanunu'nun 29. maddesi 1. fıkrasının (a) bendi gereğince yüklenilen KDV'nin iadesinin "
            "talep edilebileceği belirtilmektedir. Aynı kanunun 32. maddesi de bu kapsamda "
            "değerlendirilebilir."
        ),
        "expected_concepts": [
            {"kanun_no": "3065", "madde": "29"},
            {"kanun_no": "3065", "madde": "32"},
        ],
        "min_concept_count": 1,
    },
    {
        "gold_id": "sample_gvk_geçici_67",
        "content": (
            "Hisse senedi alım-satım kazançları için Gelir Vergisi Kanunu'nun Geçici 67'nci maddesi "
            "uyarınca tevkifat uygulaması söz konusudur. Aynı kanunun mükerrer 80'inci maddesi de "
            "değer artış kazançlarını düzenlemektedir."
        ),
        "expected_concepts": [
            {"kanun_no": "193", "madde": "Geçici 67"},
            {"kanun_no": "193", "madde": "Mükerrer 80"},
        ],
        "min_concept_count": 1,
    },
]
```

- [ ] **Step 2: Smoke-check (no test file yet — Task 3 covers matching, Task 4 covers resolver)**

Run: `.venv/bin/python -c "from backend.training.gold_docs import GOLD_DOCS; print(f'{len(GOLD_DOCS)} gold docs'); [print(g['gold_id'], '→', len(g['expected_concepts']), 'concepts') for g in GOLD_DOCS]"`

Expected output:
```
3 gold docs
sample_kvk_5 → 2 concepts
sample_kdv_29 → 2 concepts
sample_gvk_geçici_67 → 2 concepts
```

- [ ] **Step 3: Run full suite (no regressions)**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 403 PASS (no new tests yet).

- [ ] **Step 4: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/training/gold_docs.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(training): add 3 placeholder gold-doc samples

Code-baseline placeholders for the training annotation challenge — KVK
art. 5/1/a (iştirak kazançları), KDV art. 29 (ihracat KDV iadesi),
GVK Geçici 67 + Mükerrer 80. Real production gold set will be loaded
via the import-gold-docs CLI subcommand into training_gold_doc_overrides.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Pure Matching Functions (`score_quiz`, `match_gold_doc`, `is_doc_pass`)

**Goal:** Pure functions for quiz scoring + subset-semantic gold-doc matching. No DB. Heavily tested for the boundary cases (wildcard fields, missing keys, source_text ignored).

**Files:**
- Create: `backend/training/matching.py`
- Create: `tests/test_training_matching.py`

- [ ] **Step 1: Write `tests/test_training_matching.py`**

```python
"""Unit tests for training.matching pure functions."""
import pytest
from backend.training import matching


# ---- score_quiz ----

def test_score_quiz_all_correct():
    questions = [
        {"id": "q01", "correct_choice_idx": 1, "text": "?", "choices": ["a", "b", "c", "d"]},
        {"id": "q02", "correct_choice_idx": 0, "text": "?", "choices": ["a", "b", "c", "d"]},
    ]
    answers = {"q01": 1, "q02": 0}
    assert matching.score_quiz(questions, answers) == 2


def test_score_quiz_partial():
    questions = [
        {"id": "q01", "correct_choice_idx": 1, "text": "?", "choices": ["a", "b", "c", "d"]},
        {"id": "q02", "correct_choice_idx": 0, "text": "?", "choices": ["a", "b", "c", "d"]},
        {"id": "q03", "correct_choice_idx": 2, "text": "?", "choices": ["a", "b", "c", "d"]},
    ]
    answers = {"q01": 1, "q02": 3, "q03": 2}  # 2 right, 1 wrong
    assert matching.score_quiz(questions, answers) == 2


def test_score_quiz_missing_answer_counts_as_wrong():
    questions = [
        {"id": "q01", "correct_choice_idx": 1, "text": "?", "choices": ["a", "b", "c", "d"]},
        {"id": "q02", "correct_choice_idx": 0, "text": "?", "choices": ["a", "b", "c", "d"]},
    ]
    answers = {"q01": 1}  # q02 unanswered
    assert matching.score_quiz(questions, answers) == 1


def test_score_quiz_extra_answers_ignored():
    """Defensive: if frontend sends an answer for a question that isn't
    in this attempt's selection, ignore it gracefully."""
    questions = [
        {"id": "q01", "correct_choice_idx": 1, "text": "?", "choices": ["a", "b", "c", "d"]},
    ]
    answers = {"q01": 1, "q99": 0}
    assert matching.score_quiz(questions, answers) == 1


def test_score_quiz_zero_questions():
    assert matching.score_quiz([], {}) == 0


# ---- match_gold_doc + is_doc_pass ----

def _ref(**kw):
    base = {"kanun_no": "", "kanun_ad": "", "madde": "", "fikra": "", "bent": "", "source_text": ""}
    base.update(kw)
    return base


def test_match_concept_full_field_match():
    refs = [_ref(kanun_no="5520", madde="5", source_text="any text")]
    concept = {"kanun_no": "5520", "madde": "5"}
    assert matching.match_concept(concept, refs) is True


def test_match_concept_partial_field_in_concept_uses_subset_semantics():
    """concept has only kanun_no+madde. Ref has more fields filled — still matches."""
    refs = [_ref(kanun_no="5520", madde="5", fikra="1", bent="a", source_text="x")]
    concept = {"kanun_no": "5520", "madde": "5"}
    assert matching.match_concept(concept, refs) is True


def test_match_concept_extra_field_in_concept_must_match():
    """If concept demands fikra=1, ref's fikra must be 1 (or match wildcard rules)."""
    refs = [_ref(kanun_no="5520", madde="5", fikra="2")]
    concept = {"kanun_no": "5520", "madde": "5", "fikra": "1"}
    assert matching.match_concept(concept, refs) is False


def test_match_concept_empty_string_fields_in_concept_are_wildcard():
    """Empty values in concept ARE NOT match constraints."""
    refs = [_ref(kanun_no="5520", madde="5", fikra="2")]
    concept = {"kanun_no": "5520", "madde": "5", "fikra": ""}
    assert matching.match_concept(concept, refs) is True


def test_match_concept_source_text_in_concept_ignored():
    """source_text is NEVER a match constraint, even if present in concept."""
    refs = [_ref(kanun_no="5520", madde="5", source_text="totally different wording")]
    concept = {"kanun_no": "5520", "madde": "5", "source_text": "expected wording"}
    assert matching.match_concept(concept, refs) is True


def test_match_concept_no_refs():
    assert matching.match_concept({"kanun_no": "5520", "madde": "5"}, []) is False


def test_match_gold_doc_counts_distinct_concepts():
    refs = [
        _ref(kanun_no="5520", madde="5", fikra="1", bent="a"),
        _ref(kanun_no="3065", madde="29"),
    ]
    expected = [
        {"kanun_no": "5520", "madde": "5"},
        {"kanun_no": "5520", "madde": "5", "fikra": "1", "bent": "a"},
        {"kanun_no": "3065", "madde": "29"},
    ]
    summary = matching.match_gold_doc(expected, refs)
    assert summary["matched_count"] == 3
    assert summary["expected_count"] == 3


def test_match_gold_doc_missed_concept():
    refs = [_ref(kanun_no="5520", madde="5")]
    expected = [
        {"kanun_no": "5520", "madde": "5"},
        {"kanun_no": "3065", "madde": "29"},  # not in refs
    ]
    summary = matching.match_gold_doc(expected, refs)
    assert summary["matched_count"] == 1
    assert summary["expected_count"] == 2


def test_is_doc_pass_threshold():
    summary = {"matched_count": 1, "expected_count": 2}
    assert matching.is_doc_pass(summary, min_concept_count=1) is True
    assert matching.is_doc_pass(summary, min_concept_count=2) is False
    assert matching.is_doc_pass({"matched_count": 0, "expected_count": 1}, min_concept_count=1) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_training_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.training.matching'`.

- [ ] **Step 3: Implement `backend/training/matching.py`**

```python
"""Pure functions: quiz scoring + subset-semantic gold-doc concept matching.

No DB access. No side effects. Used by training.service to compute attempt
scores at submit time.

Subset-semantic concept matching contract:
  Given a concept dict `c` and a user reference dict `r`, `r` matches `c` iff:
    for every key k in c:
      if k == "source_text": skip (source_text is never a constraint)
      if c[k] is empty (None or ""): skip (empty value = wildcard)
      else: r.get(k) must equal c[k] (exact string match)

  A concept "matches" a reference list if AT LEAST ONE reference satisfies
  the above.

  A gold doc's match count = number of distinct concepts that match.
  A gold doc passes if match_count >= min_concept_count.
"""
from typing import Iterable


_IGNORED_FIELDS = ("source_text",)


def score_quiz(
    questions: Iterable[dict],
    answers: dict[str, int],
) -> int:
    """Return the count of correct answers across the given questions.

    `questions`: iterable of {"id", "correct_choice_idx", ...}.
    `answers`:   {question_id: chosen_choice_idx}.

    Missing answers count as wrong. Extra answers (for question_ids not in
    `questions`) are ignored.
    """
    score = 0
    for q in questions:
        chosen = answers.get(q["id"])
        if chosen is not None and chosen == q["correct_choice_idx"]:
            score += 1
    return score


def _concept_constraints(concept: dict) -> dict:
    """Return only the (key, value) pairs in concept that are active match
    constraints — i.e. exclude empty values and the source_text key."""
    return {
        k: v for k, v in concept.items()
        if k not in _IGNORED_FIELDS and v not in (None, "")
    }


def match_concept(concept: dict, references: Iterable[dict]) -> bool:
    """Return True iff at least one reference satisfies all constraints
    in `concept` (subset semantics)."""
    constraints = _concept_constraints(concept)
    if not constraints:
        # A concept with zero constraints is a "match anything" placeholder;
        # treat as matching iff there's at least one reference.
        return any(True for _ in references)
    for r in references:
        if all(r.get(k) == v for k, v in constraints.items()):
            return True
    return False


def match_gold_doc(
    expected_concepts: list[dict],
    references: list[dict],
) -> dict:
    """Return a summary: {matched_count, expected_count, matched_concepts}.

    `matched_concepts` is the list of concept dicts (in the order given) for
    which at least one reference matched."""
    matched: list[dict] = []
    for c in expected_concepts:
        if match_concept(c, references):
            matched.append(c)
    return {
        "matched_count": len(matched),
        "expected_count": len(expected_concepts),
        "matched_concepts": matched,
    }


def is_doc_pass(summary: dict, *, min_concept_count: int) -> bool:
    """Return True iff the user's annotation passes the gold doc's threshold."""
    return summary["matched_count"] >= min_concept_count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_training_matching.py -v`
Expected: 14 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 403 prior + 14 new = 417 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/training/matching.py tests/test_training_matching.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(training): add subset-semantic concept matching + quiz scoring

Pure functions: score_quiz counts correct answers (missing=wrong, extras
ignored). match_concept treats empty/None values in expected concepts as
wildcards and never compares source_text — so the user's annotation
wording is free as long as the concept's filled fields are present.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Hybrid Gold-Doc Resolver

**Goal:** `get_active_gold_docs(db)` — merges code baseline (`gold_docs.py`) with `training_gold_doc_overrides` table per spec lines 1007-1034.

**Files:**
- Create: `backend/training/service.py` (start with just the resolver)
- Create: `tests/test_training_resolver.py`

- [ ] **Step 1: Write `tests/test_training_resolver.py`**

```python
"""Unit tests for the hybrid gold-doc resolver."""
import json
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.training import service as training_service
from backend.training import gold_docs as code_gold


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    yield conn
    conn.close()


def _insert_override(
    conn, gold_id, *, source="override", is_deleted=0,
    content=None, expected_concepts=None, min_concept_count=None,
):
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO training_gold_doc_overrides(
            gold_id, is_deleted, content, expected_concepts, min_concept_count,
            source, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gold_id, is_deleted, content,
            json.dumps(expected_concepts) if expected_concepts is not None else None,
            min_concept_count, source, now, now,
        ),
    )


def test_no_overrides_returns_code_baseline(db):
    out = training_service.get_active_gold_docs(db)
    assert len(out) == len(code_gold.GOLD_DOCS)
    assert {d["gold_id"] for d in out} == {g["gold_id"] for g in code_gold.GOLD_DOCS}


def test_override_replaces_content_only(db):
    target = code_gold.GOLD_DOCS[0]["gold_id"]
    _insert_override(db, target, source="override", content="OVERRIDDEN TEXT")
    out = training_service.get_active_gold_docs(db)
    item = next(d for d in out if d["gold_id"] == target)
    assert item["content"] == "OVERRIDDEN TEXT"
    # expected_concepts and min_concept_count fall back to code baseline
    assert item["expected_concepts"] == code_gold.GOLD_DOCS[0]["expected_concepts"]


def test_override_replaces_expected_concepts(db):
    target = code_gold.GOLD_DOCS[0]["gold_id"]
    new_concepts = [{"kanun_no": "9999", "madde": "1"}]
    _insert_override(db, target, source="override", expected_concepts=new_concepts)
    out = training_service.get_active_gold_docs(db)
    item = next(d for d in out if d["gold_id"] == target)
    assert item["expected_concepts"] == new_concepts


def test_override_min_count_zero_is_honored(db):
    """min_concept_count=0 is a legitimate value (means: 'always pass'); the
    NULL fallback should NOT trigger when the override explicitly sets 0."""
    target = code_gold.GOLD_DOCS[0]["gold_id"]
    _insert_override(db, target, source="override", min_concept_count=0)
    out = training_service.get_active_gold_docs(db)
    item = next(d for d in out if d["gold_id"] == target)
    assert item["min_concept_count"] == 0


def test_is_deleted_excludes_baseline_entry(db):
    target = code_gold.GOLD_DOCS[0]["gold_id"]
    _insert_override(db, target, source="override", is_deleted=1)
    out = training_service.get_active_gold_docs(db)
    assert target not in {d["gold_id"] for d in out}
    # Other baseline entries still present
    assert len(out) == len(code_gold.GOLD_DOCS) - 1


def test_custom_entry_appended(db):
    _insert_override(
        db, "custom_001", source="custom",
        content="Custom doc content",
        expected_concepts=[{"kanun_no": "5520", "madde": "10"}],
        min_concept_count=1,
    )
    out = training_service.get_active_gold_docs(db)
    custom = next((d for d in out if d["gold_id"] == "custom_001"), None)
    assert custom is not None
    assert custom["content"] == "Custom doc content"
    assert custom["expected_concepts"] == [{"kanun_no": "5520", "madde": "10"}]
    assert custom["min_concept_count"] == 1


def test_custom_deleted_excluded(db):
    _insert_override(
        db, "custom_002", source="custom", is_deleted=1,
        content="x", expected_concepts=[{"kanun_no": "1"}], min_concept_count=1,
    )
    out = training_service.get_active_gold_docs(db)
    assert "custom_002" not in {d["gold_id"] for d in out}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_training_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.training.service'`.

- [ ] **Step 3: Implement `backend/training/service.py` (resolver only)**

```python
"""Training gate service.

Public API (filled progressively across Paket 10 tasks):
  get_active_gold_docs(db) -> list[dict]                       # Task 4
  start_attempt(db, *, user_id) -> dict                        # Task 5
  submit_quiz(db, *, attempt_id, user_id, answers) -> dict     # Task 5
  submit_annotation(db, *, attempt_id, user_id, gold_id,       # Task 5
                    references) -> dict
  finalize_if_complete(db, *, attempt_id, user_id) -> dict     # Task 5
  is_locked_out(db, *, user_id) -> bool                        # Task 5

The resolver merges the code baseline (`backend.training.gold_docs.GOLD_DOCS`)
with rows in the `training_gold_doc_overrides` table per spec §"Q5 hibrit
modeli" (spec lines 1007-1034).
"""
import json
import logging
import sqlite3

from backend.training import gold_docs as code_gold


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hybrid gold-doc resolver
# ---------------------------------------------------------------------------

def get_active_gold_docs(db: sqlite3.Connection) -> list[dict]:
    """Return the resolved list of gold docs available for the training
    challenge. Code baseline + DB overrides per spec lines 1007-1034.

    Resolution rules:
      - For every code-baseline entry:
          * If override row exists with is_deleted=1 → exclude.
          * If override row exists → merge: override fields win over code
            (NULL/missing in override means fall back to code).
          * Otherwise → use code entry as-is.
      - For every override row with source='custom' AND is_deleted=0 AND
        gold_id NOT in code baseline → append.
    """
    rows = db.execute(
        "SELECT gold_id, is_deleted, content, expected_concepts, "
        "min_concept_count, source FROM training_gold_doc_overrides"
    ).fetchall()
    overrides = {r["gold_id"]: r for r in rows}

    out: list[dict] = []
    seen: set[str] = set()
    for code in code_gold.GOLD_DOCS:
        gid = code["gold_id"]
        ov = overrides.get(gid)
        if ov is not None and ov["is_deleted"]:
            continue
        if ov is not None:
            content = ov["content"] if ov["content"] is not None else code["content"]
            ec_blob = ov["expected_concepts"]
            expected = json.loads(ec_blob) if ec_blob is not None else code["expected_concepts"]
            mcc = ov["min_concept_count"] if ov["min_concept_count"] is not None else code["min_concept_count"]
            out.append({
                "gold_id": gid,
                "content": content,
                "expected_concepts": expected,
                "min_concept_count": mcc,
            })
        else:
            out.append(dict(code))
        seen.add(gid)

    for gid, ov in overrides.items():
        if ov["source"] == "custom" and not ov["is_deleted"] and gid not in seen:
            out.append({
                "gold_id": gid,
                "content": ov["content"],
                "expected_concepts": json.loads(ov["expected_concepts"]) if ov["expected_concepts"] else [],
                "min_concept_count": ov["min_concept_count"] if ov["min_concept_count"] is not None else 1,
            })

    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_training_resolver.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 417 prior + 7 new = 424 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/training/service.py tests/test_training_resolver.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(training): add hybrid gold-doc resolver

get_active_gold_docs merges code baseline with training_gold_doc_overrides
rows: override fields win over code (NULL = fall back), is_deleted=1
suppresses code entries, source='custom' rows append new docs. Implements
spec §"Q5 hibrit modeli" (spec lines 1007-1034).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Attempt-State Service (start, submit_quiz, submit_annotation, finalize, lockout)

**Goal:** Append attempt-lifecycle functions to `backend/training/service.py`. The whole flow lives here — DB writes, deterministic seed-based question/doc selection, idempotency guards, and finalize logic that touches users, gamification, and notifications.

**Files:**
- Modify: `backend/training/service.py`
- Create: `tests/test_training_service.py`

- [ ] **Step 1: Write `tests/test_training_service.py`**

```python
"""Unit tests for training.service attempt lifecycle (no HTTP)."""
import json
from datetime import datetime, timezone

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations
from backend.training import service as training_service


@pytest.fixture
def db(db_path):
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO users(id, username, password_hash, role, has_seen_manual, "
        "has_passed_training, created_at, updated_at) "
        "VALUES (1, 'alice', 'x', 'user', 1, 0, ?, ?)",
        (now, now),
    )
    yield conn
    conn.close()


def _ref(**kw):
    base = {"kanun_no": "", "kanun_ad": "", "madde": "",
            "fikra": "", "bent": "", "source_text": "x"}
    base.update(kw)
    return base


# ---- start_attempt ----

def test_start_attempt_creates_row_returns_questions_and_docs(db):
    out = training_service.start_attempt(db, user_id=1)
    assert "attempt_id" in out
    assert isinstance(out["attempt_id"], int)
    assert len(out["questions"]) == 5
    # No correct_choice_idx exposed
    assert all("correct_choice_idx" not in q for q in out["questions"])
    assert len(out["gold_docs"]) == 3
    # No expected_concepts / min_concept_count exposed
    assert all("expected_concepts" not in g for g in out["gold_docs"])
    assert all("min_concept_count" not in g for g in out["gold_docs"])


def test_start_attempt_persists_attempt_row(db):
    out = training_service.start_attempt(db, user_id=1)
    row = db.execute(
        "SELECT user_id, attempt_number, quiz_total, annotation_total, passed "
        "FROM training_attempts WHERE id=?", (out["attempt_id"],),
    ).fetchone()
    assert row["user_id"] == 1
    assert row["attempt_number"] == 1
    assert row["quiz_total"] == 5
    assert row["annotation_total"] == 3
    assert row["passed"] == 0


def test_start_attempt_increments_attempt_number(db):
    a1 = training_service.start_attempt(db, user_id=1)
    a2 = training_service.start_attempt(db, user_id=1)
    row1 = db.execute("SELECT attempt_number FROM training_attempts WHERE id=?", (a1["attempt_id"],)).fetchone()
    row2 = db.execute("SELECT attempt_number FROM training_attempts WHERE id=?", (a2["attempt_id"],)).fetchone()
    assert row1["attempt_number"] == 1
    assert row2["attempt_number"] == 2


def test_start_attempt_already_passed_user_409(db):
    db.execute("UPDATE users SET has_passed_training=1 WHERE id=1")
    with pytest.raises(training_service.AlreadyPassedError):
        training_service.start_attempt(db, user_id=1)


def test_start_attempt_lockout_after_max_attempts(db):
    # Plant 3 failed attempts (default max=3)
    now = datetime.now(timezone.utc).isoformat()
    for n in range(1, 4):
        db.execute(
            "INSERT INTO training_attempts(user_id, attempt_number, quiz_score, "
            "quiz_total, annotation_pass_count, annotation_total, passed, started_at, "
            "finished_at) VALUES (1, ?, 0, 5, 0, 3, 0, ?, ?)",
            (n, now, now),
        )
    with pytest.raises(training_service.LockedOutError):
        training_service.start_attempt(db, user_id=1)


def test_start_attempt_seed_is_deterministic(db):
    """Same attempt_id → same questions and gold doc selection."""
    out = training_service.start_attempt(db, user_id=1)
    questions_a = training_service._select_questions_for_attempt(out["attempt_id"])
    questions_b = training_service._select_questions_for_attempt(out["attempt_id"])
    assert [q["id"] for q in questions_a] == [q["id"] for q in questions_b]


# ---- submit_quiz ----

def test_submit_quiz_scores_and_persists(db):
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    # Answer all correctly
    answers = {q["id"]: q["correct_choice_idx"] for q in selected}
    result = training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1, answers=answers,
    )
    assert result["score"] == 5
    assert result["total"] == 5
    row = db.execute(
        "SELECT quiz_score FROM training_attempts WHERE id=?", (out["attempt_id"],),
    ).fetchone()
    assert row["quiz_score"] == 5


def test_submit_quiz_partial_score(db):
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    answers = {q["id"]: (q["correct_choice_idx"] + 1) % 4 for q in selected}  # all wrong
    result = training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1, answers=answers,
    )
    assert result["score"] == 0


def test_submit_quiz_idempotent_409_on_resubmit(db):
    """Re-submitting quiz for the same attempt is a 409 conflict."""
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    answers = {q["id"]: q["correct_choice_idx"] for q in selected}
    training_service.submit_quiz(db, attempt_id=out["attempt_id"], user_id=1, answers=answers)
    with pytest.raises(training_service.QuizAlreadySubmittedError):
        training_service.submit_quiz(db, attempt_id=out["attempt_id"], user_id=1, answers=answers)


def test_submit_quiz_zero_score_can_still_submit_once(db):
    """Zero score is the legitimate first submission — must NOT trigger the
    idempotency guard. Guard logic must use a separate marker, not quiz_score>0."""
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    bad_answers = {q["id"]: (q["correct_choice_idx"] + 1) % 4 for q in selected}
    result = training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1, answers=bad_answers,
    )
    assert result["score"] == 0


def test_submit_quiz_wrong_user_403(db):
    """Submitting another user's attempt is a 403/AccessDenied."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO users(id, username, password_hash, role, has_seen_manual, "
        "has_passed_training, created_at, updated_at) "
        "VALUES (2, 'bob', 'x', 'user', 1, 0, ?, ?)",
        (now, now),
    )
    out = training_service.start_attempt(db, user_id=1)
    with pytest.raises(training_service.AttemptNotOwnedError):
        training_service.submit_quiz(
            db, attempt_id=out["attempt_id"], user_id=2, answers={},
        )


# ---- submit_annotation ----

def test_submit_annotation_first_doc_persists(db):
    out = training_service.start_attempt(db, user_id=1)
    docs = training_service._select_gold_docs_for_attempt(db, out["attempt_id"])
    gid = docs[0]["gold_id"]
    refs = [_ref(kanun_no="5520", madde="5", source_text="x")]
    result = training_service.submit_annotation(
        db, attempt_id=out["attempt_id"], user_id=1, gold_id=gid, references=refs,
    )
    assert "passed" in result
    assert "matched_count" in result
    row = db.execute(
        "SELECT annotation_details_json FROM training_attempts WHERE id=?",
        (out["attempt_id"],),
    ).fetchone()
    details = json.loads(row["annotation_details_json"])
    assert gid in details


def test_submit_annotation_unknown_gold_id_404(db):
    out = training_service.start_attempt(db, user_id=1)
    with pytest.raises(training_service.GoldDocNotInAttemptError):
        training_service.submit_annotation(
            db, attempt_id=out["attempt_id"], user_id=1,
            gold_id="not_in_this_attempt", references=[],
        )


def test_submit_annotation_resubmit_same_doc_409(db):
    out = training_service.start_attempt(db, user_id=1)
    docs = training_service._select_gold_docs_for_attempt(db, out["attempt_id"])
    gid = docs[0]["gold_id"]
    training_service.submit_annotation(
        db, attempt_id=out["attempt_id"], user_id=1, gold_id=gid, references=[],
    )
    with pytest.raises(training_service.GoldDocAlreadySubmittedError):
        training_service.submit_annotation(
            db, attempt_id=out["attempt_id"], user_id=1, gold_id=gid, references=[],
        )


# ---- finalize_if_complete ----

def test_finalize_does_nothing_when_quiz_or_docs_missing(db):
    out = training_service.start_attempt(db, user_id=1)
    final = training_service.finalize_if_complete(db, attempt_id=out["attempt_id"], user_id=1)
    assert final is None  # not yet complete
    user = db.execute("SELECT has_passed_training FROM users WHERE id=1").fetchone()
    assert user["has_passed_training"] == 0


def test_finalize_marks_passed_when_all_thresholds_met(db):
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    docs = training_service._select_gold_docs_for_attempt(db, out["attempt_id"])

    # Quiz: all correct
    training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1,
        answers={q["id"]: q["correct_choice_idx"] for q in selected},
    )
    # Annotate: pass 2 of 3 (one with a real concept hit, one with a real concept hit, one empty)
    for i, doc in enumerate(docs):
        ref = _ref(
            kanun_no=doc["expected_concepts"][0].get("kanun_no", ""),
            madde=doc["expected_concepts"][0].get("madde", ""),
            source_text="x",
        ) if i < 2 else _ref()
        training_service.submit_annotation(
            db, attempt_id=out["attempt_id"], user_id=1,
            gold_id=doc["gold_id"], references=[ref] if i < 2 else [],
        )
    # 3rd submission should auto-finalize
    user = db.execute("SELECT has_passed_training FROM users WHERE id=1").fetchone()
    assert user["has_passed_training"] == 1
    row = db.execute(
        "SELECT passed, annotation_pass_count FROM training_attempts WHERE id=?",
        (out["attempt_id"],),
    ).fetchone()
    assert row["passed"] == 1
    assert row["annotation_pass_count"] == 2


def test_finalize_awards_xp_and_notification(db):
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    docs = training_service._select_gold_docs_for_attempt(db, out["attempt_id"])

    training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1,
        answers={q["id"]: q["correct_choice_idx"] for q in selected},
    )
    for i, doc in enumerate(docs):
        ref = _ref(
            kanun_no=doc["expected_concepts"][0].get("kanun_no", ""),
            madde=doc["expected_concepts"][0].get("madde", ""),
        ) if i < 2 else _ref()
        training_service.submit_annotation(
            db, attempt_id=out["attempt_id"], user_id=1,
            gold_id=doc["gold_id"], references=[ref] if i < 2 else [],
        )
    # Gamification ledger gained a +50 row with reason='training_pass'
    ledger = db.execute(
        "SELECT delta_xp, reason FROM gamification_ledger WHERE user_id=1 "
        "AND reason='training_pass'",
    ).fetchall()
    assert len(ledger) == 1
    assert ledger[0]["delta_xp"] == 50

    # Notification persisted
    notifs = db.execute(
        "SELECT kind, title FROM notifications WHERE user_id=1 AND kind='training_passed'"
    ).fetchall()
    assert len(notifs) == 1
    assert "Tebrikler" in notifs[0]["title"]


def test_finalize_fail_does_not_award_xp_or_pass_user(db):
    out = training_service.start_attempt(db, user_id=1)
    selected = training_service._select_questions_for_attempt(out["attempt_id"])
    docs = training_service._select_gold_docs_for_attempt(db, out["attempt_id"])

    # Quiz: all wrong → score 0, below threshold 4
    training_service.submit_quiz(
        db, attempt_id=out["attempt_id"], user_id=1,
        answers={q["id"]: (q["correct_choice_idx"] + 1) % 4 for q in selected},
    )
    for doc in docs:
        training_service.submit_annotation(
            db, attempt_id=out["attempt_id"], user_id=1,
            gold_id=doc["gold_id"], references=[],
        )
    user = db.execute("SELECT has_passed_training FROM users WHERE id=1").fetchone()
    assert user["has_passed_training"] == 0
    row = db.execute(
        "SELECT passed FROM training_attempts WHERE id=?", (out["attempt_id"],),
    ).fetchone()
    assert row["passed"] == 0
    # No training_pass XP
    ledger = db.execute(
        "SELECT COUNT(*) AS c FROM gamification_ledger WHERE reason='training_pass'"
    ).fetchone()
    assert ledger["c"] == 0


# ---- is_locked_out ----

def test_is_locked_out_below_max_attempts(db):
    now = datetime.now(timezone.utc).isoformat()
    for n in range(1, 3):  # 2 attempts (under 3-default-max)
        db.execute(
            "INSERT INTO training_attempts(user_id, attempt_number, quiz_score, "
            "quiz_total, annotation_pass_count, annotation_total, passed, started_at, "
            "finished_at) VALUES (1, ?, 0, 5, 0, 3, 0, ?, ?)",
            (n, now, now),
        )
    assert training_service.is_locked_out(db, user_id=1) is False


def test_is_locked_out_at_max_attempts_no_pass(db):
    now = datetime.now(timezone.utc).isoformat()
    for n in range(1, 4):
        db.execute(
            "INSERT INTO training_attempts(user_id, attempt_number, quiz_score, "
            "quiz_total, annotation_pass_count, annotation_total, passed, started_at, "
            "finished_at) VALUES (1, ?, 0, 5, 0, 3, 0, ?, ?)",
            (n, now, now),
        )
    assert training_service.is_locked_out(db, user_id=1) is True


def test_is_locked_out_passed_user_not_locked(db):
    """A user who already passed isn't 'locked out' — they're done. Lockout
    only matters if user hasn't passed AND has exhausted attempts."""
    now = datetime.now(timezone.utc).isoformat()
    for n in range(1, 4):
        passed = 1 if n == 3 else 0
        db.execute(
            "INSERT INTO training_attempts(user_id, attempt_number, quiz_score, "
            "quiz_total, annotation_pass_count, annotation_total, passed, started_at, "
            "finished_at) VALUES (1, ?, 0, 5, 0, 3, ?, ?, ?)",
            (n, passed, now, now),
        )
    assert training_service.is_locked_out(db, user_id=1) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_training_service.py -v`
Expected: FAIL — most attribute errors (start_attempt, etc. not defined).

- [ ] **Step 3: Append the attempt-lifecycle code to `backend/training/service.py`**

Insert AFTER `get_active_gold_docs`:

```python
# ---------------------------------------------------------------------------
# Attempt lifecycle — service exceptions
# ---------------------------------------------------------------------------

class TrainingServiceError(Exception):
    """Base for all training service exceptions."""


class AlreadyPassedError(TrainingServiceError):
    """User already has has_passed_training=1; can't retake."""


class LockedOutError(TrainingServiceError):
    """User has reached max_attempts without passing. Admin reset required."""


class AttemptNotOwnedError(TrainingServiceError):
    """The given attempt_id doesn't belong to the calling user."""


class AttemptNotFoundError(TrainingServiceError):
    """No training_attempts row for this id."""


class QuizAlreadySubmittedError(TrainingServiceError):
    """Quiz already submitted for this attempt — idempotency guard."""


class GoldDocNotInAttemptError(TrainingServiceError):
    """The supplied gold_id wasn't selected for this attempt."""


class GoldDocAlreadySubmittedError(TrainingServiceError):
    """This gold_id was already annotated within this attempt."""


# ---------------------------------------------------------------------------
# Deterministic selection (attempt_id is the seed)
# ---------------------------------------------------------------------------

import random
from datetime import datetime, timezone
from typing import Optional

from backend.shared import settings as S
from backend.shared import audit
from backend.training import quiz_data
from backend.training import matching
from backend.gamification import service as gamification_service
from backend.notifications import service as notif_service


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _select_questions_for_attempt(attempt_id: int) -> list[dict]:
    """Pick 5 deterministic questions seeded by attempt_id."""
    rng = random.Random(attempt_id)
    return rng.sample(quiz_data.QUIZ_QUESTIONS, 5)


def _select_gold_docs_for_attempt(db: sqlite3.Connection, attempt_id: int) -> list[dict]:
    """Pick 3 deterministic gold docs seeded by attempt_id, drawn from the
    resolved active pool (code baseline + DB overrides)."""
    pool = get_active_gold_docs(db)
    if len(pool) < 3:
        # In production, the user's CLI-imported docs + 3 placeholders
        # always satisfies this. Defensive: fall back to whatever is available.
        return pool
    rng = random.Random(attempt_id)
    return rng.sample(pool, 3)


def _strip_correct_answers(questions: list[dict]) -> list[dict]:
    return [
        {"id": q["id"], "text": q["text"], "choices": q["choices"]}
        for q in questions
    ]


def _strip_gold_answers(docs: list[dict]) -> list[dict]:
    return [
        {"gold_id": d["gold_id"], "content": d["content"]}
        for d in docs
    ]


# ---------------------------------------------------------------------------
# Attempt lifecycle
# ---------------------------------------------------------------------------

def is_locked_out(db: sqlite3.Connection, *, user_id: int) -> bool:
    """True iff user has used >= max_attempts AND none passed."""
    max_attempts = S.get_int(db, "training.max_attempts", default=3)
    rows = db.execute(
        "SELECT passed FROM training_attempts WHERE user_id=?", (user_id,),
    ).fetchall()
    if not rows:
        return False
    if any(r["passed"] == 1 for r in rows):
        return False
    return len(rows) >= max_attempts


def _user_passed(db: sqlite3.Connection, user_id: int) -> bool:
    row = db.execute(
        "SELECT has_passed_training FROM users WHERE id=?", (user_id,),
    ).fetchone()
    return bool(row and row["has_passed_training"])


def _attempt_row(db: sqlite3.Connection, attempt_id: int) -> Optional[dict]:
    row = db.execute(
        "SELECT * FROM training_attempts WHERE id=?", (attempt_id,),
    ).fetchone()
    return dict(row) if row else None


def _verify_owner(db: sqlite3.Connection, attempt_id: int, user_id: int) -> dict:
    """Return attempt row dict; raise AttemptNotOwnedError or AttemptNotFoundError."""
    row = _attempt_row(db, attempt_id)
    if row is None:
        raise AttemptNotFoundError(attempt_id)
    if row["user_id"] != user_id:
        raise AttemptNotOwnedError(attempt_id)
    return row


def start_attempt(db: sqlite3.Connection, *, user_id: int) -> dict:
    """Begin a new training attempt for the user.

    Raises:
      AlreadyPassedError — user.has_passed_training already 1
      LockedOutError    — user has used max_attempts without passing
    """
    if _user_passed(db, user_id):
        raise AlreadyPassedError(user_id)
    if is_locked_out(db, user_id=user_id):
        raise LockedOutError(user_id)

    # Compute next attempt_number
    row = db.execute(
        "SELECT COUNT(*) AS c FROM training_attempts WHERE user_id=?", (user_id,),
    ).fetchone()
    attempt_number = row["c"] + 1
    now = _now_utc_iso()

    cur = db.execute(
        """
        INSERT INTO training_attempts(
            user_id, attempt_number, quiz_score, quiz_total,
            annotation_pass_count, annotation_total, annotation_details_json,
            passed, started_at, finished_at
        ) VALUES (?, ?, 0, 5, 0, 3, NULL, 0, ?, ?)
        """,
        (user_id, attempt_number, now, now),
    )
    attempt_id = cur.lastrowid
    assert attempt_id is not None  # SQLite always returns an id on successful INSERT

    questions = _select_questions_for_attempt(attempt_id)
    docs = _select_gold_docs_for_attempt(db, attempt_id)

    audit.log_activity(
        db, user_id=user_id, event_type="training_start",
        extra={"attempt_id": attempt_id, "attempt_number": attempt_number},
    )
    return {
        "attempt_id": attempt_id,
        "attempt_number": attempt_number,
        "questions": _strip_correct_answers(questions),
        "gold_docs": _strip_gold_answers(docs),
    }


def submit_quiz(
    db: sqlite3.Connection,
    *,
    attempt_id: int,
    user_id: int,
    answers: dict[str, int],
) -> dict:
    """Score the quiz portion. Idempotent: re-submit raises QuizAlreadySubmittedError."""
    row = _verify_owner(db, attempt_id, user_id)
    # Idempotency: we use a marker in annotation_details_json — but quiz also has
    # a "submitted" flag. Since the schema lacks a dedicated column, we encode
    # it as: a non-null annotation_details_json with `_quiz_submitted` key.
    details = json.loads(row["annotation_details_json"]) if row["annotation_details_json"] else {}
    if details.get("_quiz_submitted"):
        raise QuizAlreadySubmittedError(attempt_id)

    questions = _select_questions_for_attempt(attempt_id)
    score = matching.score_quiz(questions, answers)

    details["_quiz_submitted"] = True
    details["_quiz_score"] = score
    db.execute(
        "UPDATE training_attempts SET quiz_score=?, annotation_details_json=? WHERE id=?",
        (score, json.dumps(details), attempt_id),
    )
    finalize_if_complete(db, attempt_id=attempt_id, user_id=user_id)
    return {"score": score, "total": 5}


def submit_annotation(
    db: sqlite3.Connection,
    *,
    attempt_id: int,
    user_id: int,
    gold_id: str,
    references: list[dict],
) -> dict:
    """Score one gold doc. Idempotent: re-submit same gold_id raises
    GoldDocAlreadySubmittedError. Auto-finalizes when 3rd distinct doc lands."""
    _verify_owner(db, attempt_id, user_id)
    selected_docs = _select_gold_docs_for_attempt(db, attempt_id)
    by_id = {d["gold_id"]: d for d in selected_docs}
    if gold_id not in by_id:
        raise GoldDocNotInAttemptError(gold_id)

    row = _verify_owner(db, attempt_id, user_id)
    details = json.loads(row["annotation_details_json"]) if row["annotation_details_json"] else {}
    if gold_id in details and isinstance(details[gold_id], dict):
        raise GoldDocAlreadySubmittedError(gold_id)

    doc = by_id[gold_id]
    summary = matching.match_gold_doc(doc["expected_concepts"], references)
    passed = matching.is_doc_pass(summary, min_concept_count=doc["min_concept_count"])
    details[gold_id] = {
        "passed": passed,
        "matched_count": summary["matched_count"],
        "expected_count": summary["expected_count"],
    }

    # Recompute annotation_pass_count from details
    pass_count = sum(
        1 for k, v in details.items()
        if not k.startswith("_") and isinstance(v, dict) and v.get("passed")
    )

    db.execute(
        "UPDATE training_attempts SET annotation_pass_count=?, annotation_details_json=? WHERE id=?",
        (pass_count, json.dumps(details), attempt_id),
    )
    finalize_if_complete(db, attempt_id=attempt_id, user_id=user_id)
    return {
        "passed": passed,
        "matched_count": summary["matched_count"],
        "expected_count": summary["expected_count"],
        "min_concept_count": doc["min_concept_count"],
    }


def finalize_if_complete(
    db: sqlite3.Connection, *, attempt_id: int, user_id: int,
) -> Optional[dict]:
    """Check if both quiz + 3 docs submitted; if so, compute pass and apply
    user/gamification/notification side-effects. Returns the finalize summary
    or None if not yet complete. Idempotent — finalize is a no-op if attempt
    is already passed=1 or fail-final."""
    row = _attempt_row(db, attempt_id)
    if row is None:
        return None
    if row["passed"] == 1:
        return None  # already finalized as pass

    details = json.loads(row["annotation_details_json"]) if row["annotation_details_json"] else {}
    if not details.get("_quiz_submitted"):
        return None
    doc_keys = [k for k in details if not k.startswith("_") and isinstance(details[k], dict)]
    if len(doc_keys) < 3:
        return None
    if details.get("_finalized"):
        return None  # already finalized as fail

    quiz_threshold = S.get_int(db, "training.quiz_pass_threshold", default=4)
    anno_threshold = S.get_int(db, "training.annotation_pass_threshold", default=2)
    quiz_pass = row["quiz_score"] >= quiz_threshold
    anno_pass = row["annotation_pass_count"] >= anno_threshold
    overall_pass = quiz_pass and anno_pass

    now = _now_utc_iso()
    details["_finalized"] = True
    db.execute(
        "UPDATE training_attempts SET passed=?, finished_at=?, annotation_details_json=? WHERE id=?",
        (1 if overall_pass else 0, now, json.dumps(details), attempt_id),
    )

    if overall_pass:
        try:
            db.execute("UPDATE users SET has_passed_training=1 WHERE id=?", (user_id,))
        except Exception:
            log.exception("flip has_passed_training failed for user %s", user_id)
        try:
            xp_delta = S.get_int(db, "gamification.xp_training_pass", default=50)
            gamification_service.award_xp(
                db, user_id=user_id, delta_xp=xp_delta,
                reason="training_pass", related_doc_id=None,
            )
        except Exception:
            log.exception("training_pass xp award failed for user %s", user_id)
        try:
            notif_service.create(
                db, user_id=user_id, kind="training_passed",
                title="Tebrikler! Eğitimi geçtin",
                body=f"Bursiyer eğitimini başarıyla tamamladın. +{S.get_int(db, 'gamification.xp_training_pass', default=50)} XP kazandın.",
                data={"attempt_id": attempt_id},
            )
        except Exception:
            log.exception("training_pass notification create failed")
        try:
            audit.log_activity(
                db, user_id=user_id, event_type="training_pass",
                extra={"attempt_id": attempt_id},
            )
        except Exception:
            log.exception("training_pass audit log failed")
    else:
        try:
            audit.log_activity(
                db, user_id=user_id, event_type="training_fail",
                extra={
                    "attempt_id": attempt_id,
                    "quiz_score": row["quiz_score"],
                    "annotation_pass_count": row["annotation_pass_count"],
                },
            )
        except Exception:
            log.exception("training_fail audit log failed")

    return {
        "passed": overall_pass,
        "quiz_score": row["quiz_score"],
        "quiz_total": 5,
        "annotation_pass_count": row["annotation_pass_count"],
        "annotation_total": 3,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_training_service.py -v`
Expected: 17 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 424 prior + 17 new = 441 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/training/service.py tests/test_training_service.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(training): add attempt lifecycle (start, submit_quiz, submit_annotation, finalize)

attempt_id is the deterministic seed for question + gold-doc selection;
server holds no per-attempt session state. Idempotency: re-submitting the
quiz or the same gold-doc is 409. Auto-finalize on 3rd distinct doc:
checks both thresholds, flips has_passed_training=1, awards +50 XP via
gamification, persists training_passed notification, logs audit. Each
side-effect is fault-isolated. Lockout = max_attempts reached without
pass — admin reset (Paket 11) clears.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: HTTP Routes + End-to-End Pass Test

**Goal:** Three FastAPI endpoints + a single end-to-end integration test that drives the full HTTP pass flow. Mount the router in `main.py`.

**Files:**
- Create: `backend/training/models.py`
- Create: `backend/training/routes.py`
- Modify: `backend/main.py`
- Create: `tests/test_training_routes.py`
- Create: `tests/test_training_pass_integration.py`

- [ ] **Step 1: Write `backend/training/models.py`**

```python
"""Pydantic schemas for the training endpoints."""
from typing import Optional

from pydantic import BaseModel, Field


class QuestionOut(BaseModel):
    id: str
    text: str
    choices: list[str]


class GoldDocOut(BaseModel):
    gold_id: str
    content: str


class StartResponse(BaseModel):
    attempt_id: int
    attempt_number: int
    questions: list[QuestionOut]
    gold_docs: list[GoldDocOut]


class QuizSubmitRequest(BaseModel):
    attempt_id: int
    answers: dict[str, int]


class QuizSubmitResponse(BaseModel):
    score: int
    total: int


class AnnotateSubmitRequest(BaseModel):
    attempt_id: int
    gold_id: str
    references: list[dict]


class AnnotateSubmitResponse(BaseModel):
    passed: bool
    matched_count: int
    expected_count: int
    min_concept_count: int


class OkResponse(BaseModel):
    ok: bool = True
```

- [ ] **Step 2: Write `backend/training/routes.py`**

```python
"""HTTP endpoints for the training gate. Auth: require_seen_manual.

The user is taking training right now — using require_passed_training would
be circular. Pre-manual users (has_seen_manual=0) still must read /help first."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.training import service
from backend.training.models import (
    StartResponse, QuizSubmitRequest, QuizSubmitResponse,
    AnnotateSubmitRequest, AnnotateSubmitResponse,
)
from backend.users.deps import get_db, require_seen_manual


router = APIRouter(prefix="/api/training", tags=["training"])


@router.get("/start", response_model=StartResponse)
def start(
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_seen_manual),
):
    """Begin a new training attempt. 409 if user already passed; 403 if locked out."""
    try:
        return service.start_attempt(db, user_id=user["id"])
    except service.AlreadyPassedError:
        raise HTTPException(
            status_code=409,
            detail={"error": "already_passed", "message": "user already passed training"},
        )
    except service.LockedOutError:
        raise HTTPException(
            status_code=403,
            detail={"error": "max_attempts_reached", "message": "max attempts used; admin reset required"},
        )


@router.post("/quiz/submit", response_model=QuizSubmitResponse)
def submit_quiz(
    payload: QuizSubmitRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_seen_manual),
):
    try:
        return service.submit_quiz(
            db, attempt_id=payload.attempt_id, user_id=user["id"],
            answers=payload.answers,
        )
    except service.AttemptNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "attempt_not_found"})
    except service.AttemptNotOwnedError:
        raise HTTPException(status_code=403, detail={"error": "attempt_not_owned"})
    except service.QuizAlreadySubmittedError:
        raise HTTPException(status_code=409, detail={"error": "quiz_already_submitted"})


@router.post("/annotate/submit", response_model=AnnotateSubmitResponse)
def submit_annotation(
    payload: AnnotateSubmitRequest,
    db: sqlite3.Connection = Depends(get_db),
    user: sqlite3.Row = Depends(require_seen_manual),
):
    try:
        return service.submit_annotation(
            db, attempt_id=payload.attempt_id, user_id=user["id"],
            gold_id=payload.gold_id, references=payload.references,
        )
    except service.AttemptNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "attempt_not_found"})
    except service.AttemptNotOwnedError:
        raise HTTPException(status_code=403, detail={"error": "attempt_not_owned"})
    except service.GoldDocNotInAttemptError:
        raise HTTPException(status_code=404, detail={"error": "gold_doc_not_in_attempt"})
    except service.GoldDocAlreadySubmittedError:
        raise HTTPException(status_code=409, detail={"error": "gold_doc_already_submitted"})
```

- [ ] **Step 3: Write `tests/test_training_routes.py`**

```python
"""HTTP-level tests for /api/training/* endpoints."""
from backend.shared.db import connect
from backend import config


def _seen_manual_user(client, username="u_train"):
    """Register + login a user with has_seen_manual=1, has_passed_training=0."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            (f"INV-{username}",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": username, "password": "password123",
        "invite_code": f"INV-{username}",
    })
    assert r.status_code == 201
    user = r.json()
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET has_seen_manual=1, has_passed_training=0 WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/login", json={
        "username": username, "password": "password123",
    })
    assert r.status_code == 200
    return user


def test_start_requires_auth(client):
    r = client.get("/api/training/start")
    assert r.status_code == 401


def test_start_pre_manual_user_409(client):
    """User who hasn't seen manual yet gets 409 (manual_not_seen)."""
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            ("INV-PRE",),
        )
    finally:
        conn.close()
    client.post("/api/auth/register", json={
        "username": "u_pre", "password": "password123", "invite_code": "INV-PRE",
    })
    client.post("/api/auth/login", json={"username": "u_pre", "password": "password123"})
    r = client.get("/api/training/start")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "manual_not_seen"


def test_start_returns_5_questions_and_3_gold_docs(client):
    _seen_manual_user(client, "u_start1")
    r = client.get("/api/training/start")
    assert r.status_code == 200
    data = r.json()
    assert "attempt_id" in data
    assert len(data["questions"]) == 5
    assert len(data["gold_docs"]) == 3
    # No leaks
    for q in data["questions"]:
        assert "correct_choice_idx" not in q
    for g in data["gold_docs"]:
        assert "expected_concepts" not in g


def test_start_409_when_already_passed(client):
    user = _seen_manual_user(client, "u_done")
    conn = connect(config.DB_PATH)
    try:
        conn.execute("UPDATE users SET has_passed_training=1 WHERE id=?", (user["id"],))
    finally:
        conn.close()
    r = client.get("/api/training/start")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "already_passed"


def test_start_403_when_locked_out(client):
    user = _seen_manual_user(client, "u_locked")
    conn = connect(config.DB_PATH)
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        for n in range(1, 4):
            conn.execute(
                "INSERT INTO training_attempts(user_id, attempt_number, quiz_score, "
                "quiz_total, annotation_pass_count, annotation_total, passed, started_at, "
                "finished_at) VALUES (?, ?, 0, 5, 0, 3, 0, ?, ?)",
                (user["id"], n, now, now),
            )
    finally:
        conn.close()
    r = client.get("/api/training/start")
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "max_attempts_reached"


def test_quiz_submit_unknown_attempt_404(client):
    _seen_manual_user(client, "u_qs1")
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": 9999, "answers": {},
    })
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "attempt_not_found"


def test_quiz_submit_wrong_user_403(client):
    user_a = _seen_manual_user(client, "u_qa")
    r = client.get("/api/training/start")
    aid = r.json()["attempt_id"]
    # Switch to a different user
    client.cookies.clear()
    _seen_manual_user(client, "u_qb")
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": aid, "answers": {},
    })
    assert r.status_code == 403


def test_quiz_submit_idempotent_409(client):
    _seen_manual_user(client, "u_qid")
    r = client.get("/api/training/start")
    aid = r.json()["attempt_id"]
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": aid, "answers": {},
    })
    assert r.status_code == 200
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": aid, "answers": {},
    })
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "quiz_already_submitted"


def test_annotate_submit_unknown_gold_id_404(client):
    _seen_manual_user(client, "u_an1")
    r = client.get("/api/training/start")
    aid = r.json()["attempt_id"]
    r = client.post("/api/training/annotate/submit", json={
        "attempt_id": aid, "gold_id": "not_in_attempt", "references": [],
    })
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "gold_doc_not_in_attempt"


def test_annotate_submit_resubmit_409(client):
    _seen_manual_user(client, "u_an2")
    r = client.get("/api/training/start")
    aid = r.json()["attempt_id"]
    gid = r.json()["gold_docs"][0]["gold_id"]
    r = client.post("/api/training/annotate/submit", json={
        "attempt_id": aid, "gold_id": gid, "references": [],
    })
    assert r.status_code == 200
    r = client.post("/api/training/annotate/submit", json={
        "attempt_id": aid, "gold_id": gid, "references": [],
    })
    assert r.status_code == 409
```

- [ ] **Step 4: Mount the router in `backend/main.py`**

Add the import (alphabetical, near other domain imports):

```python
from backend.training.routes import router as training_router
```

And below the other `app.include_router(...)` lines:

```python
app.include_router(training_router)
```

- [ ] **Step 5: Write `tests/test_training_pass_integration.py`**

```python
"""End-to-end pass flow through HTTP.

Drives the full happy path:
  1. start → get attempt_id + 5 questions + 3 gold docs
  2. quiz submit with all-correct answers
  3. annotate submit for each of 3 docs (with refs that hit ≥1 expected concept)
  4. assert: user.has_passed_training=1, +50 XP ledger row, training_passed notification
"""
from backend.shared.db import connect
from backend import config


def _seen_manual_user(client, username="u_e2e"):
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "INSERT INTO invite_codes(code, is_active, created_at) VALUES (?,1,datetime('now'))",
            (f"INV-{username}",),
        )
    finally:
        conn.close()
    r = client.post("/api/auth/register", json={
        "username": username, "password": "password123",
        "invite_code": f"INV-{username}",
    })
    user = r.json()
    conn = connect(config.DB_PATH)
    try:
        conn.execute(
            "UPDATE users SET has_seen_manual=1, has_passed_training=0 WHERE id=?",
            (user["id"],),
        )
    finally:
        conn.close()
    client.post("/api/auth/login", json={
        "username": username, "password": "password123",
    })
    return user


def _ref(**kw):
    base = {"kanun_no": "", "kanun_ad": "", "madde": "",
            "fikra": "", "bent": "", "source_text": "x"}
    base.update(kw)
    return base


def test_full_pass_flow(client):
    user = _seen_manual_user(client, "u_full")

    # 1. start
    r = client.get("/api/training/start")
    assert r.status_code == 200
    data = r.json()
    aid = data["attempt_id"]

    # 2. Quiz: get the correct answers via the service's helper (test-only access
    #    to the deterministic selection — frontend obviously doesn't have this).
    from backend.training.service import _select_questions_for_attempt
    questions = _select_questions_for_attempt(aid)
    answers = {q["id"]: q["correct_choice_idx"] for q in questions}
    r = client.post("/api/training/quiz/submit", json={
        "attempt_id": aid, "answers": answers,
    })
    assert r.status_code == 200
    assert r.json()["score"] == 5

    # 3. Annotate each doc with a ref hitting first expected concept
    from backend.training.service import _select_gold_docs_for_attempt
    conn = connect(config.DB_PATH)
    try:
        docs = _select_gold_docs_for_attempt(conn, aid)
    finally:
        conn.close()
    for d in docs:
        c = d["expected_concepts"][0]
        ref = _ref(
            kanun_no=c.get("kanun_no", ""),
            madde=c.get("madde", ""),
            fikra=c.get("fikra", ""),
            bent=c.get("bent", ""),
            source_text="dummy text",
        )
        r = client.post("/api/training/annotate/submit", json={
            "attempt_id": aid, "gold_id": d["gold_id"], "references": [ref],
        })
        assert r.status_code == 200
        assert r.json()["passed"] is True

    # 4. Side-effects
    conn = connect(config.DB_PATH)
    try:
        urow = conn.execute(
            "SELECT has_passed_training FROM users WHERE id=?", (user["id"],),
        ).fetchone()
        assert urow["has_passed_training"] == 1

        ledger = conn.execute(
            "SELECT delta_xp FROM gamification_ledger "
            "WHERE user_id=? AND reason='training_pass'", (user["id"],),
        ).fetchall()
        assert len(ledger) == 1
        assert ledger[0]["delta_xp"] == 50

        notif = conn.execute(
            "SELECT title FROM notifications WHERE user_id=? AND kind='training_passed'",
            (user["id"],),
        ).fetchone()
        assert notif is not None
        assert "Tebrikler" in notif["title"]
    finally:
        conn.close()


def test_fail_flow_keeps_user_pre_training(client):
    """All quiz answers wrong → finalize fails → user stays has_passed_training=0."""
    user = _seen_manual_user(client, "u_fail")
    r = client.get("/api/training/start")
    aid = r.json()["attempt_id"]

    from backend.training.service import _select_questions_for_attempt
    questions = _select_questions_for_attempt(aid)
    bad = {q["id"]: (q["correct_choice_idx"] + 1) % 4 for q in questions}
    client.post("/api/training/quiz/submit", json={"attempt_id": aid, "answers": bad})

    for d in r.json()["gold_docs"]:
        client.post("/api/training/annotate/submit", json={
            "attempt_id": aid, "gold_id": d["gold_id"], "references": [],
        })

    conn = connect(config.DB_PATH)
    try:
        urow = conn.execute(
            "SELECT has_passed_training FROM users WHERE id=?", (user["id"],),
        ).fetchone()
    finally:
        conn.close()
    assert urow["has_passed_training"] == 0
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_training_routes.py tests/test_training_pass_integration.py -v`
Expected: all PASS (10 routes + 2 integration = 12).

- [ ] **Step 7: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 441 prior + 12 new = 453 PASS.

- [ ] **Step 8: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/training/models.py backend/training/routes.py backend/main.py tests/test_training_routes.py tests/test_training_pass_integration.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(training): add 3 HTTP endpoints + end-to-end pass test

GET /api/training/start, POST /api/training/quiz/submit, POST
/api/training/annotate/submit. Auth: require_seen_manual (NOT
require_passed_training — circular). End-to-end test drives full pass
flow: start → quiz → 3 docs → assert has_passed_training=1, +50 XP,
training_passed notification.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: CLI `import-gold-docs` Subcommand

**Goal:** `python -m backend.cli import-gold-docs <path>` reads a JSON file matching the documented format and INSERT-OR-REPLACEs `training_gold_doc_overrides` rows with `source='custom'`. Lets the user swap placeholder docs for their real 5-6 production gold docs.

**Files:**
- Modify: `backend/cli.py`
- Create: `tests/test_cli_import_gold_docs.py`

- [ ] **Step 1: Look at current `backend/cli.py` structure**

Run: `.venv/bin/python -c "import inspect; from backend import cli; print(inspect.getsource(cli)[:2000])"`
Expected output: shows the existing argparse subcommands (e.g. `migrate`, `ingest`, `bootstrap-admin`).

This step is informational — the next step modifies the file based on this. Note the existing pattern (subparser per command).

- [ ] **Step 2: Write `tests/test_cli_import_gold_docs.py`**

```python
"""CLI tests for `python -m backend.cli import-gold-docs <path>`."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from backend.shared.db import connect
from backend.migrations import discover_migrations
from backend.migrations.runner import apply_migrations


@pytest.fixture
def fresh_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Run migrations to set up the schema
    db_path = tmp_path / "db" / "annotations.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    apply_migrations(conn, discover_migrations())
    conn.close()
    return tmp_path


def _run_cli(*args, env_extra=None):
    env = {"PYTHONPATH": str(Path(__file__).parent.parent), **(env_extra or {})}
    return subprocess.run(
        [sys.executable, "-m", "backend.cli", *args],
        capture_output=True, text=True, env={**__import__("os").environ, **env},
    )


def test_import_creates_custom_overrides(fresh_data_dir):
    payload = {
        "gold_docs": [
            {
                "gold_id": "real_001",
                "content": "Gerçek özelge metni 1.",
                "expected_concepts": [{"kanun_no": "5520", "madde": "5"}],
                "min_concept_count": 1,
            },
            {
                "gold_id": "real_002",
                "content": "Gerçek özelge metni 2.",
                "expected_concepts": [
                    {"kanun_no": "3065", "madde": "29", "fikra": "1", "bent": "a"},
                ],
                "min_concept_count": 1,
            },
        ],
    }
    json_path = fresh_data_dir / "gold.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False))

    result = _run_cli("import-gold-docs", str(json_path), env_extra={"DATA_DIR": str(fresh_data_dir)})
    assert result.returncode == 0, result.stderr
    assert "imported 2" in result.stdout.lower() or "2" in result.stdout

    conn = connect(fresh_data_dir / "db" / "annotations.db")
    try:
        rows = conn.execute(
            "SELECT gold_id, source, content, expected_concepts, min_concept_count "
            "FROM training_gold_doc_overrides ORDER BY gold_id"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 2
    assert rows[0]["gold_id"] == "real_001"
    assert rows[0]["source"] == "custom"
    assert rows[0]["content"] == "Gerçek özelge metni 1."
    assert json.loads(rows[0]["expected_concepts"]) == [{"kanun_no": "5520", "madde": "5"}]
    assert rows[0]["min_concept_count"] == 1


def test_import_idempotent_overwrites_existing(fresh_data_dir):
    """Running import twice with the same gold_id replaces the row."""
    payload_v1 = {"gold_docs": [{
        "gold_id": "real_001", "content": "v1",
        "expected_concepts": [{"kanun_no": "1"}],
        "min_concept_count": 1,
    }]}
    payload_v2 = {"gold_docs": [{
        "gold_id": "real_001", "content": "v2",
        "expected_concepts": [{"kanun_no": "2"}],
        "min_concept_count": 2,
    }]}
    p = fresh_data_dir / "gold.json"
    p.write_text(json.dumps(payload_v1))
    _run_cli("import-gold-docs", str(p), env_extra={"DATA_DIR": str(fresh_data_dir)})
    p.write_text(json.dumps(payload_v2))
    result = _run_cli("import-gold-docs", str(p), env_extra={"DATA_DIR": str(fresh_data_dir)})
    assert result.returncode == 0

    conn = connect(fresh_data_dir / "db" / "annotations.db")
    try:
        row = conn.execute(
            "SELECT content, min_concept_count FROM training_gold_doc_overrides WHERE gold_id=?",
            ("real_001",),
        ).fetchone()
    finally:
        conn.close()
    assert row["content"] == "v2"
    assert row["min_concept_count"] == 2


def test_import_invalid_json_returns_nonzero(fresh_data_dir):
    p = fresh_data_dir / "bad.json"
    p.write_text("{not valid json}")
    result = _run_cli("import-gold-docs", str(p), env_extra={"DATA_DIR": str(fresh_data_dir)})
    assert result.returncode != 0
    assert "json" in result.stderr.lower() or "json" in result.stdout.lower()


def test_import_missing_required_field_returns_nonzero(fresh_data_dir):
    payload = {"gold_docs": [{"gold_id": "no_content_no_concepts"}]}
    p = fresh_data_dir / "bad.json"
    p.write_text(json.dumps(payload))
    result = _run_cli("import-gold-docs", str(p), env_extra={"DATA_DIR": str(fresh_data_dir)})
    assert result.returncode != 0
```

- [ ] **Step 3: Add `import-gold-docs` subparser to `backend/cli.py`**

Read the file first (it's small), then add a new subparser block. The new code should:
- Add a `import-gold-docs` subparser with one positional `path` argument.
- Implement a `_cmd_import_gold_docs(args)` function that:
  - Loads JSON from path; on parse error, prints to stderr and exits 1.
  - Validates each entry has `gold_id`, `content`, `expected_concepts`, `min_concept_count`. On missing field, prints to stderr and exits 1.
  - Opens DB connection via `backend.shared.db.connect(config.DB_PATH)`.
  - For each gold_doc entry, runs `INSERT OR REPLACE INTO training_gold_doc_overrides(...) VALUES (?, 0, ?, ?, ?, 'custom', ?, ?)`.
  - Prints `imported N gold-doc(s) into training_gold_doc_overrides` to stdout.

The exact code to add:

```python
def _cmd_import_gold_docs(args) -> int:
    import json as _json
    from datetime import datetime, timezone
    from backend.shared.db import connect
    from backend import config

    path = args.path
    try:
        with open(path, encoding="utf-8") as f:
            payload = _json.load(f)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    except _json.JSONDecodeError as e:
        print(f"error: invalid JSON in {path}: {e}", file=sys.stderr)
        return 1

    docs = payload.get("gold_docs")
    if not isinstance(docs, list):
        print("error: payload must have a top-level 'gold_docs' list", file=sys.stderr)
        return 1

    required = ("gold_id", "content", "expected_concepts", "min_concept_count")
    for i, d in enumerate(docs):
        for k in required:
            if k not in d:
                print(f"error: gold_docs[{i}] missing required field '{k}'", file=sys.stderr)
                return 1

    config.ensure_dirs()
    conn = connect(config.DB_PATH)
    try:
        now = datetime.now(timezone.utc).isoformat()
        for d in docs:
            conn.execute(
                """
                INSERT OR REPLACE INTO training_gold_doc_overrides(
                    gold_id, is_deleted, content, expected_concepts,
                    min_concept_count, source, created_at, updated_at
                ) VALUES (?, 0, ?, ?, ?, 'custom', ?, ?)
                """,
                (
                    d["gold_id"], d["content"],
                    _json.dumps(d["expected_concepts"]),
                    d["min_concept_count"],
                    now, now,
                ),
            )
    finally:
        conn.close()

    print(f"imported {len(docs)} gold-doc(s) into training_gold_doc_overrides")
    return 0
```

And in the argparse setup section (look for how other subparsers are added — there should be a `subparsers.add_parser(...)` block):

```python
    p_import_gold = subparsers.add_parser(
        "import-gold-docs",
        help="Import gold docs from a JSON file into training_gold_doc_overrides as source='custom'.",
    )
    p_import_gold.add_argument("path", help="path to gold-docs JSON file")
    p_import_gold.set_defaults(func=_cmd_import_gold_docs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli_import_gold_docs.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/python -m pytest -x -q`
Expected: 453 prior + 4 new = 457 PASS.

- [ ] **Step 6: Commit**

```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add backend/cli.py tests/test_cli_import_gold_docs.py
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
feat(cli): add import-gold-docs subcommand

Reads a JSON file with shape {"gold_docs": [{gold_id, content,
expected_concepts, min_concept_count}, ...]} and INSERT-OR-REPLACEs
into training_gold_doc_overrides with source='custom'. Idempotent —
re-running with same gold_id swaps the row. The hybrid resolver in
training.service then merges these with the code-baseline placeholders.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Polish + Tag

**Goal:** Final cleanup pass + `paket-10-training-gate` tag.

- [ ] **Step 1: Inspect for dead code / drift**

Run:
```bash
.venv/bin/python -m pytest -q
git diff main --stat
```

Look for and clean up:
- Unused imports anywhere in `backend/training/`. The `Optional` import on `service.py` and the `Field` import on `models.py` were both planned for use — verify they're actually referenced.
- Any leftover `# TODO` markers or print statements.
- Pyright-only warnings (cosmetic; can ignore unless trivially fixable).

- [ ] **Step 2: Verify OpenAPI surface**

Run:
```bash
.venv/bin/python -c "
from backend.main import app
paths = sorted(p for p in app.openapi()['paths'])
for p in paths:
    if 'training' in p:
        print(p)
"
```
Expected output:
```
/api/training/annotate/submit
/api/training/quiz/submit
/api/training/start
```

- [ ] **Step 3: Run full suite one final time**

Run: `.venv/bin/python -m pytest -q`
Expected: ~457 PASS.

- [ ] **Step 4: Commit any polish + tag**

If polish changes were made:
```bash
git -c user.email=maarkval@icloud.com -c user.name=baran add -A
git -c user.email=maarkval@icloud.com -c user.name=baran commit -m "$(cat <<'EOF'
chore(paket10): polish — drop unused imports, docstrings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Note: do NOT add the untracked planning markdown files in `docs/superpowers/plans/` — they are tracked separately. Use targeted `git add` for source files only.

Tag:
```bash
git tag paket-10-training-gate
git log --oneline -12
git tag --list 'paket-*'
```

Expected: `paket-10-training-gate` appears alongside paket-1 through paket-9.

---

## Out of Scope / Follow-ups

- **Admin override of quiz questions:** The static `quiz_data.QUIZ_QUESTIONS` is the source of truth for Paket 10. Admin UI (Paket 11) will let admins edit/disable individual questions via a similar override pattern (new table or extension of existing `training_gold_doc_overrides`-style).
- **Training reset endpoint:** `POST /api/admin/training/{user_id}/reset` (spec line 706) is Paket 11. Cleared by deleting all `training_attempts` rows for the user.
- **Live SSE event for `training_pass`:** Currently the `notification` SSE only fires when the `gamification.run_after_save` orchestrator publishes via `_publish_unlock_events`. Training pass writes a notification row directly via `notif_service.create` — no SSE delivery for online users. The frontend training screen receives the pass result in the response body anyway, so this is acceptable for Paket 10. Add a `await sse_broker.publish_to([user_id], "notification", {...})` call at finalize time if a future pass needs live delivery.
- **`audit.log_activity` event types `training_start`, `training_pass`, `training_fail`** are introduced here for the first time. Paket 11 admin audit log viewer needs to know these (no schema change required — they're just strings).
- **Concurrent training attempts:** The schema doesn't prevent a user from having two `training_attempts` rows in 'in-progress' state simultaneously. Out of scope here — frontend won't generate this scenario.
- **User's real gold docs (5-6 expected):** When ready, the user provides a JSON file with the documented shape; running `python -m backend.cli import-gold-docs <path>` swaps placeholder selections for the real ones (via `source='custom'` rows; placeholders remain as code baseline but the resolver pool grows). For a stricter "use ONLY production gold docs" stance, also delete the placeholders by inserting `is_deleted=1, source='override'` overrides for each `sample_*` gold_id.
