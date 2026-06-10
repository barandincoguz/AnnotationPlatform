# Citation Validation and Normalization Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen legal citation reference quality by adding auto-splitting, name abbreviation matching, verbal ordinal parsing, bent cleaning, and generic row suppression across both frontend and backend.

**Architecture:** Normalization logic is mirrored on both sides: the backend Pydantic models split and clean values on request instantiation, and the frontend cleans/splits fields on UI component inputs during blur events.

**Tech Stack:** React 18, TypeScript, Python 3.13, Pydantic v2, FastAPI, SQLite

---

### Task 1: Fix Pre-Existing Test Failures

**Files:**
- Modify: `tests/test_schema.py:83-91`
- Run: `python -m scripts.regen_neon_ddl`

- [ ] **Step 1: Update v0008 in schema idempotency test**
  Modify [tests/test_schema.py:L88](file:///Users/barandincoguz/Desktop/AnnotationProgram/tests/test_schema.py#L88) to include `"v0008"`:
  ```python
  # Target content inside test_all_migrations_idempotent
  assert first == ["v0001", "v0002", "v0003", "v0004", "v0005", "v0006", "v0007", "v0008"]
  ```

- [ ] **Step 2: Regenerate Postgres DDL**
  Run: `python -m scripts.regen_neon_ddl`
  Expected output: Success, updating the generated DDL schema.

- [ ] **Step 3: Run schema and Postgres DDL tests**
  Run: `pytest tests/test_schema.py tests/test_mirror_postgres_ddl.py -v`
  Expected output: PASS

- [ ] **Step 4: Commit test fixes**
  Run:
  ```bash
  git add tests/test_schema.py migrations/postgres/001-baran-init.sql
  git commit -m "test: fix pre-existing migration schema and DDL drift assertions"
  ```

---

### Task 2: Backend Normalization Helpers in `diff.py`

**Files:**
- Modify: `backend/annotations/diff.py`
- Modify: `tests/test_annotations_diff.py`

- [ ] **Step 1: Write backend unit tests for new normalization rules**
  Add the following tests to the end of [tests/test_annotations_diff.py](file:///Users/barandincoguz/Desktop/AnnotationProgram/tests/test_annotations_diff.py):
  ```python
  def test_normalize_identifier():
      from backend.annotations.diff import normalize_identifier
      assert normalize_identifier("birinci") == "1"
      assert normalize_identifier("ikinci") == "2"
      assert normalize_identifier("(a)") == "a"
      assert normalize_identifier("[b]") == "b"
      assert normalize_identifier("a.") == "a"
      assert normalize_identifier(None) is None

  def test_normalize_kanun_adi():
      from backend.annotations.diff import normalize_kanun_adi
      assert normalize_kanun_adi("KVK") == "Kurumlar Vergisi Kanunu"
      assert normalize_kanun_adi("GVK") == "Gelir Vergisi Kanunu"
      assert normalize_kanun_adi("VUK") == "Vergi Usul Kanunu"
      assert normalize_kanun_adi("Kanun") == "Kanun"
      assert normalize_kanun_adi(None) is None

  def test_parse_madde_token():
      from backend.annotations.diff import parse_madde_token
      assert parse_madde_token("16/1-a") == ("16", "1", "a")
      assert parse_madde_token("5-a") == ("5", "", "a")
      assert parse_madde_token("13/a") == ("13", "", "a")  # No 13/a special exception
      assert parse_madde_token("16/1") == ("16", "1", "")
      assert parse_madde_token("5") == ("5", "", "")
      assert parse_madde_token(None) == ("", "", "")

  def test_normalize_reference_with_complex_madde():
      from backend.annotations.diff import normalize_reference
      ref = {"source_text": "x", "madde": "16/1-a"}
      normalized = normalize_reference(ref)
      assert normalized["madde"] == "16"
      assert normalized["fikra"] == "1"
      assert normalized["bent"] == "a"

  def test_generic_reference_suppression():
      from backend.annotations.diff import normalize_references
      refs = [
          {"source_text": "general text", "kanun_no": "5520"},
          {"source_text": "specific text", "kanun_no": "5520", "madde": "5"},
      ]
      normalized = normalize_references(refs)
      # The generic reference should be suppressed, leaving only the specific one
      assert len(normalized) == 1
      assert normalized[0]["madde"] == "5"
  ```

- [ ] **Step 2: Run tests and verify they fail**
  Run: `pytest tests/test_annotations_diff.py -v`
  Expected: FAIL (ImportErrors or AssertionErrors due to missing logic)

- [ ] **Step 3: Implement validation & normalization logic in diff.py**
  Replace the entire content of [backend/annotations/diff.py](file:///Users/barandincoguz/Desktop/AnnotationProgram/backend/annotations/diff.py) with the following code:
  ```python
  """Pure-function reference normalization, deduping, and set-semantic diff."""
  import re
  import unicodedata
  from typing import Optional

  REFERENCE_FIELDS = (
      "kanun_no", "kanun_ad", "madde", "fikra", "bent", "source_text",
  )

  ORDINAL_MAP = {
      "birinci": "1",
      "ikinci": "2",
      "ucuncu": "3",
      "dorduncu": "4",
      "besinci": "5",
      "altinci": "6",
      "yedinci": "7",
      "sekizinci": "8",
      "dokuzuncu": "9",
      "onuncu": "10",
  }

  LAW_ABBREVIATIONS = {
      "VUK": "Vergi Usul Kanunu",
      "GVK": "Gelir Vergisi Kanunu",
      "KDVK": "Katma Değer Vergisi Kanunu",
      "KDV": "Katma Değer Vergisi Kanunu",
      "KVK": "Kurumlar Vergisi Kanunu",
      "OTVK": "Özel Tüketim Vergisi Kanunu",
      "OTV": "Özel Tüketim Vergisi Kanunu",
      "DVK": "Damga Vergisi Kanunu",
  }

  LAW_NAME_ALIASES = {
      "VERGIUSULKANUNU": "Vergi Usul Kanunu",
      "GELIRVERGISIKANUNU": "Gelir Vergisi Kanunu",
      "KURUMLARVERGISIKANUNU": "Kurumlar Vergisi Kanunu",
      "KATMADEGERVERGISIKANUNU": "Katma Değer Vergisi Kanunu",
      "KATMADEGERVERGISIKDVKANUNU": "Katma Değer Vergisi Kanunu",
      "KDVKANUNU": "Katma Değer Vergisi Kanunu",
      "OZELTUKETIMVERGISIKANUNU": "Özel Tüketim Vergisi Kanunu",
      "OTVKANUNU": "Özel Tüketim Vergisi Kanunu",
      "DAMGAVERGISIKANUNU": "Damga Vergisi Kanunu",
      "HARCLARKANUNU": "Harçlar Kanunu",
  }

  RE_NON_NO_CHARS = re.compile(r"[^0-9A-Za-z/-]+")
  RE_MULTI_SPACE = re.compile(r"\s+")

  class InvalidReference(ValueError):
      """source_text missing or empty."""

  class DuplicateReference(ValueError):
      """Two refs in the same list have identical canonical keys."""

  def _clean(value: Optional[object]) -> Optional[str]:
      if value is None:
          return None
      s = str(value).strip()
      return s if s else None

  def collapse_ws(text: str) -> str:
      return RE_MULTI_SPACE.sub(" ", text).strip()

  def normalize_kanun_no(value: Optional[str]) -> Optional[str]:
      if not value:
          return None
      cleaned = RE_NON_NO_CHARS.sub("", collapse_ws(str(value)))
      cleaned = cleaned.strip("/-")
      return cleaned if cleaned else None

  def _normalize_turkish_key(text: str) -> str:
      value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
      value = re.sub(r"[^A-Za-z0-9]+", "", value).upper()
      return value

  def normalize_kanun_adi(text: Optional[str], kanun_no: str = "") -> Optional[str]:
      if not text:
          return None
      raw = collapse_ws(text)
      upper_key = _normalize_turkish_key(raw)
      if upper_key in LAW_ABBREVIATIONS:
          return LAW_ABBREVIATIONS[upper_key]
      if upper_key in LAW_NAME_ALIASES:
          return LAW_NAME_ALIASES[upper_key]
      return raw

  def normalize_identifier(value: Optional[str]) -> Optional[str]:
      if not value:
          return None
      raw = collapse_ws(str(value)).strip("()[]{}., ")
      lowered = _normalize_turkish_key(raw).lower()
      return ORDINAL_MAP.get(lowered, raw)

  def normalize_madde(value: Optional[str]) -> Optional[str]:
      if not value:
          return None
      raw = collapse_ws(str(value))
      raw = re.sub(r"^madd\w*\s+", "", raw, flags=re.IGNORECASE)
      raw = re.sub(r"\s*madd\w*$", "", raw, flags=re.IGNORECASE)
      raw = raw.strip(" .()")
      return raw if raw else None

  def parse_madde_token(token: Optional[str]) -> tuple[str, str, str]:
      cleaned = normalize_madde(token)
      if not cleaned:
          return "", "", ""
      head = cleaned
      fikra = ""
      bent = ""

      if "/" in cleaned:
          left, right = cleaned.split("/", 1)
          head = left.strip()
          right = right.strip()
          if "-" in right:
              first, second = right.split("-", 1)
              if first.isdigit():
                  fikra = first
                  bent = normalize_identifier(second)
              else:
                  bent = normalize_identifier(right)
          elif right.isdigit():
              fikra = right
          else:
              bent = normalize_identifier(right)
      elif "-" in cleaned:
          left, right = cleaned.split("-", 1)
          head = left.strip()
          bent = normalize_identifier(right)

      return head, fikra, bent

  def normalize_reference(ref: dict) -> dict:
      source_text = _clean(ref.get("source_text"))
      if not source_text:
          raise InvalidReference("source_text is required")

      kanun_no = normalize_kanun_no(_clean(ref.get("kanun_no")))
      kanun_ad = normalize_kanun_adi(_clean(ref.get("kanun_ad")), kanun_no=kanun_no or "")

      madde_raw = _clean(ref.get("madde"))
      fikra_raw = _clean(ref.get("fikra"))
      bent_raw = _clean(ref.get("bent"))

      madde_val, fikra_val, bent_val = "", "", ""
      if madde_raw:
          madde_val, fikra_val, bent_val = parse_madde_token(madde_raw)

      out_madde = madde_val if madde_val else madde_raw
      out_fikra = fikra_val if fikra_val else fikra_raw
      out_bent = bent_val if bent_val else bent_raw

      return {
          "kanun_no": kanun_no if kanun_no else None,
          "kanun_ad": kanun_ad if kanun_ad else None,
          "madde": normalize_madde(out_madde) if out_madde else None,
          "fikra": normalize_identifier(out_fikra) if out_fikra else None,
          "bent": normalize_identifier(out_bent) if out_bent else None,
          "source_text": source_text,
      }

  def canonical_key(ref: dict) -> tuple:
      return tuple(ref.get(f) for f in REFERENCE_FIELDS)

  def normalize_references(refs: list[dict]) -> list[dict]:
      seen: set[tuple] = set()
      normalized_list: list[dict] = []
      for r in refs:
          n = normalize_reference(r)
          key = canonical_key(n)
          if key in seen:
              raise DuplicateReference(
                  f"duplicate reference: source_text={n['source_text']!r}"
              )
          seen.add(key)
          normalized_list.append(n)

      def law_family_key(ref: dict) -> str:
          k_no = ref.get("kanun_no")
          k_ad = ref.get("kanun_ad")
          if k_no:
              return f"no:{k_no}"
          if k_ad:
              val = _normalize_turkish_key(k_ad)
              return f"name:{val}"
          return ""

      def is_specific(ref: dict) -> bool:
          return bool(ref.get("madde") or ref.get("fikra") or ref.get("bent"))

      groups: dict[str, list[dict]] = {}
      ungrouped: list[dict] = []
      for r in normalized_list:
          fkey = law_family_key(r)
          if fkey:
              groups.setdefault(fkey, []).append(r)
          else:
              ungrouped.append(r)

      final_list: list[dict] = []
      for fkey, group in groups.items():
          specifics = [r for r in group if is_specific(r)]
          generics = [r for r in group if not is_specific(r)]
          if specifics:
              final_list.extend(group if not generics else specifics)
          else:
              final_list.extend(group)

      final_list.extend(ungrouped)

      final_keys = {canonical_key(r) for r in final_list}
      return [r for r in normalized_list if canonical_key(r) in final_keys]

  def references_diff(prev: list[dict], curr: list[dict]) -> dict:
      prev_map = {canonical_key(r): r for r in prev}
      curr_map = {canonical_key(r): r for r in curr}
      added_keys = curr_map.keys() - prev_map.keys()
      removed_keys = prev_map.keys() - curr_map.keys()
      return {
          "added": [curr_map[k] for k in added_keys],
          "removed": [prev_map[k] for k in removed_keys],
      }

  def is_diff_zero(diff: dict) -> bool:
      return not diff["added"] and not diff["removed"]
  ```

- [ ] **Step 4: Run unit tests and verify they pass**
  Run: `pytest tests/test_annotations_diff.py -v`
  Expected output: PASS

- [ ] **Step 5: Commit backend helper changes**
  Run:
  ```bash
  git add backend/annotations/diff.py tests/test_annotations_diff.py
  git commit -m "feat(normalize): implement shared backend normalizers and generic suppression"
  ```

---

### Task 3: Backend Pydantic Request Deserializer Validation

**Files:**
- Modify: `backend/annotations/models.py`
- Modify: `tests/test_annotations_routes.py` (or other routes/models test files to verify Pydantic)

- [ ] **Step 1: Write test to verify request-level deserialization and splitting**
  Add this unit test to the end of [tests/test_annotations_routes.py](file:///Users/barandincoguz/Desktop/AnnotationProgram/tests/test_annotations_routes.py):
  ```python
  def test_pydantic_reference_item_pre_normalization():
      from backend.annotations.models import ReferenceItem
      # Test auto-splitting on instantiation
      item = ReferenceItem(source_text="lorem", madde="16/1-a")
      assert item.madde == "16"
      assert item.fikra == "1"
      assert item.bent == "a"

      # Test ordinal mapping
      item2 = ReferenceItem(source_text="lorem", fikra="birinci", bent="(a)")
      assert item2.fikra == "1"
      assert item2.bent == "a"

      # Test invalid complex format rejection
      import pydantic
      with pytest.raises(pydantic.ValidationError):
          ReferenceItem(source_text="lorem", madde="16/1/a-b")
  ```

- [ ] **Step 2: Run tests and verify they fail**
  Run: `pytest tests/test_annotations_routes.py::test_pydantic_reference_item_pre_normalization -v`
  Expected: FAIL

- [ ] **Step 3: Modify Pydantic model ReferenceItem in models.py**
  Add the pre-normalization `@model_validator(mode='before')` and format validator `@model_validator(mode='after')` to `ReferenceItem` in [backend/annotations/models.py:L6-L16](file:///Users/barandincoguz/Desktop/AnnotationProgram/backend/annotations/models.py#L6-L16):
  ```python
  class ReferenceItem(BaseModel):
      kanun_no: Optional[str] = Field(default=None, max_length=64)
      kanun_ad: Optional[str] = Field(default=None, max_length=512)
      madde: Optional[str] = Field(default=None, max_length=64)
      fikra: Optional[str] = Field(default=None, max_length=64)
      bent: Optional[str] = Field(default=None, max_length=64)
      source_text: str = Field(min_length=1, max_length=4_000)

      @model_validator(mode='before')
      @classmethod
      def pre_normalize(cls, data: any) -> any:
          if isinstance(data, dict):
              from backend.annotations.diff import (
                  parse_madde_token, normalize_kanun_no, normalize_kanun_adi,
                  normalize_identifier, normalize_madde
              )
              src = data.get("source_text")
              if src is not None:
                  data["source_text"] = str(src).strip()

              madde = data.get("madde")
              if madde is not None:
                  madde_str = str(madde).strip()
                  if madde_str:
                      m, f, b = parse_madde_token(madde_str)
                      if m:
                          data["madde"] = m
                          if f:
                              data["fikra"] = f
                          if b:
                              data["bent"] = b
                      else:
                          data["madde"] = normalize_madde(madde_str)

              for f in ("kanun_no", "kanun_ad", "fikra", "bent"):
                  if f in data and data[f] is not None:
                      s = str(data[f]).strip()
                      data[f] = s if s else None

              if data.get("kanun_no"):
                  data["kanun_no"] = normalize_kanun_no(data["kanun_no"])
              if data.get("kanun_ad"):
                  data["kanun_ad"] = normalize_kanun_adi(data["kanun_ad"], kanun_no=data.get("kanun_no") or "")
              if data.get("fikra"):
                  data["fikra"] = normalize_identifier(data["fikra"])
              if data.get("bent"):
                  data["bent"] = normalize_identifier(data["bent"])

          return data

      @model_validator(mode='after')
      def validate_madde_format(self) -> "ReferenceItem":
          if self.madde and ("/" in self.madde or "-" in self.madde):
              raise ValueError("madde format is invalid. Complex formats like 5/1-a must be split.")
          return self
  ```

- [ ] **Step 4: Run tests and verify they pass**
  Run: `pytest tests/test_annotations_routes.py -v`
  Expected output: PASS

- [ ] **Step 5: Commit Pydantic model validation changes**
  Run:
  ```bash
  git add backend/annotations/models.py tests/test_annotations_routes.py
  git commit -m "feat(validation): add request-level pre-normalization and validation validators to ReferenceItem Pydantic model"
  ```

---

### Task 4: Frontend validateReferences Helper Implementations

**Files:**
- Modify: `frontend/src/lib/validateReferences.ts`
- Modify: `frontend/src/lib/validateReferences.test.ts`

- [ ] **Step 1: Write frontend unit tests for normalizers**
  Replace unit tests at the end of [frontend/src/lib/validateReferences.test.ts:L146-L172](file:///Users/barandincoguz/Desktop/AnnotationProgram/frontend/src/lib/validateReferences.test.ts#L146-L172) with:
  ```typescript
  describe('normalizeTurkishKey', () => {
    it('normalizes Turkish characters to uppercase ascii alphanumeric keys', () => {
      expect(normalizeTurkishKey('ıİğĞüÜşŞöÖçÇ')).toBe('IIGGUUSSOOCC')
    })
  })

  describe('normalizeKanunAdi', () => {
    it('expands known law name abbreviations', () => {
      expect(normalizeKanunAdi('KVK')).toBe('Kurumlar Vergisi Kanunu')
      expect(normalizeKanunAdi('GVK')).toBe('Gelir Vergisi Kanunu')
      expect(normalizeKanunAdi('VUK')).toBe('Vergi Usul Kanunu')
    })
    it('returns raw text if unknown name', () => {
      expect(normalizeKanunAdi('Özel Kanun')).toBe('Özel Kanun')
      expect(normalizeKanunAdi(null)).toBeNull()
    })
  })

  describe('normalizeIdentifier', () => {
    it('normalizes verbal Turkish ordinal words', () => {
      expect(normalizeIdentifier('birinci')).toBe('1')
      expect(normalizeIdentifier('ikinci')).toBe('2')
    })
    it('cleans parentheses and brackets', () => {
      expect(normalizeIdentifier('(a)')).toBe('a')
      expect(normalizeIdentifier('[b]')).toBe('b')
      expect(normalizeIdentifier('c.')).toBe('c')
    })
    it('returns null for empty strings', () => {
      expect(normalizeIdentifier('')).toBeNull()
    })
  })

  describe('parseComplexMadde', () => {
    it('splits complex madde formats correctly', () => {
      expect(parseComplexMadde('16/1-a')).toEqual({
        madde: '16',
        fikra: '1',
        bent: 'a',
      })
      expect(parseComplexMadde('5-a')).toEqual({
        madde: '5',
        fikra: null,
        bent: 'a',
      })
      expect(parseComplexMadde('13/a')).toEqual({
        madde: '13',
        fikra: null,
        bent: 'a',
      })
    })
  })
  ```

- [ ] **Step 2: Run frontend tests and verify they fail**
  Run: `npm run test:run`
  Expected: FAIL

- [ ] **Step 3: Update validateReferences.ts with TS normalizers**
  Replace the contents of [frontend/src/lib/validateReferences.ts](file:///Users/barandincoguz/Desktop/AnnotationProgram/frontend/src/lib/validateReferences.ts) with the following:
  ```typescript
  import type { components } from '@/api/types'

  type ReferenceItem = components['schemas']['ReferenceItem']

  export interface ParsedReference {
    madde: string | null
    fikra: string | null
    bent: string | null
  }

  const ORDINAL_MAP: Record<string, string> = {
    birinci: '1',
    ikinci: '2',
    ucuncu: '3',
    dorduncu: '4',
    besinci: '5',
    altinci: '6',
    yedinci: '7',
    sekizinci: '8',
    dokuzuncu: '9',
    onuncu: '10',
  }

  const LAW_ABBREVIATIONS: Record<string, string> = {
    VUK: 'Vergi Usul Kanunu',
    GVK: 'Gelir Vergisi Kanunu',
    KDVK: 'Katma Değer Vergisi Kanunu',
    KDV: 'Katma Değer Vergisi Kanunu',
    KVK: 'Kurumlar Vergisi Kanunu',
    OTVK: 'Özel Tüketim Vergisi Kanunu',
    OTV: 'Özel Tüketim Vergisi Kanunu',
    DVK: 'Damga Vergisi Kanunu',
  }

  const LAW_NAME_ALIASES: Record<string, string> = {
    VERGIUSULKANUNU: 'Vergi Usul Kanunu',
    GELIRVERGISIKANUNU: 'Gelir Vergisi Kanunu',
    KURUMLARVERGISIKANUNU: 'Kurumlar Vergisi Kanunu',
    KATMADEGERVERGISIKANUNU: 'Katma Değer Vergisi Kanunu',
    KATMADEGERVERGISIKDVKANUNU: 'Katma Değer Vergisi Kanunu',
    KDVKANUNU: 'Katma Değer Vergisi Kanunu',
    OZELTUKETIMVERGISIKANUNU: 'Özel Tüketim Vergisi Kanunu',
    OTVKANUNU: 'Özel Tüketim Vergisi Kanunu',
    DAMGAVERGISIKANUNU: 'Damga Vergisi Kanunu',
    HARCLARKANUNU: 'Harçlar Kanunu',
  }

  export function normalizeTurkishKey(text: string): string {
    return text
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9]/g, '')
      .toUpperCase()
  }

  export function normalizeKanunAdi(text: string | null): string | null {
    if (!text) return null
    const trimmed = text.trim()
    const upperKey = normalizeTurkishKey(trimmed)
    if (LAW_ABBREVIATIONS[upperKey]) {
      return LAW_ABBREVIATIONS[upperKey]
    }
    if (LAW_NAME_ALIASES[upperKey]) {
      return LAW_NAME_ALIASES[upperKey]
    }
    return trimmed || null
  }

  export function normalizeIdentifier(val: string | null): string | null {
    if (!val) return null
    const cleaned = val.replace(/^[()[\]\s]+|[()[\]\s]+$/g, '')
    const key = normalizeTurkishKey(cleaned).toLowerCase()
    return ORDINAL_MAP[key] || cleaned || null
  }

  export function normalizeMadde(val: string | null): string | null {
    if (!val) return null
    let cleaned = val.trim()
    cleaned = cleaned.replace(/^madd\w*\s+/i, '')
    cleaned = cleaned.replace(/\s*madd\w*$/i, '')
    cleaned = cleaned.replace(/(?:[iıuü]nc[iıuü]|nc[iıuü])$/i, '')
    return cleaned.trim() || null
  }

  export function cleanBent(val: string | null): string | null {
    return normalizeIdentifier(val)
  }

  export function parseComplexMadde(input: string): ParsedReference | null {
    const trimmed = input.trim()
    if (!trimmed) return null
    if (!trimmed.includes('/') && !trimmed.includes('-')) {
      return null
    }

    if (trimmed.includes('/')) {
      const parts = trimmed.split('/')
      const madde = normalizeMadde(parts[0])
      const remainder = parts[1] ? parts[1].trim() : ''
      if (remainder.includes('-')) {
        const subParts = remainder.split('-')
        const first = subParts[0].trim()
        const second = subParts[1].trim()
        if (/^\d+$/.test(first)) {
          return {
            madde: madde,
            fikra: first,
            bent: normalizeIdentifier(second),
          }
        } else {
          return {
            madde: madde,
            fikra: null,
            bent: normalizeIdentifier(remainder),
          }
        }
      } else if (/^\d+$/.test(remainder)) {
        return {
          madde: madde,
          fikra: remainder,
          bent: null,
        }
      } else {
        return {
          madde: madde,
          fikra: null,
          bent: normalizeIdentifier(remainder),
        }
      }
    } else {
      const parts = trimmed.split('-')
      return {
        madde: normalizeMadde(parts[0]),
        fikra: null,
        bent: normalizeIdentifier(parts[1]),
      }
    }
  }

  export function emptyReferenceItem(): ReferenceItem {
    return {
      kanun_no: null,
      kanun_ad: null,
      madde: null,
      fikra: null,
      bent: null,
      source_text: '',
    }
  }

  function hasAtLeastOneKanunField(r: ReferenceItem): boolean {
    const hasKanunNo = (r.kanun_no?.trim() ?? '') !== ''
    const hasKanunAd = (r.kanun_ad?.trim() ?? '') !== ''
    return hasKanunNo || hasKanunAd
  }

  export function isValidReference(r: ReferenceItem): boolean {
    if (!r.source_text || r.source_text.trim().length === 0) return false
    if (r.madde && (r.madde.includes('/') || r.madde.includes('-'))) {
      return false
    }
    return hasAtLeastOneKanunField(r)
  }

  export function areAllReferencesValid(refs: ReferenceItem[]): boolean {
    return refs.every(isValidReference)
  }

  export function isValidTrainingReference(r: ReferenceItem): boolean {
    return hasAtLeastOneKanunField(r)
  }

  export function areAllTrainingReferencesValid(refs: ReferenceItem[]): boolean {
    return refs.every(isValidTrainingReference)
  }
  ```

- [ ] **Step 4: Run frontend tests and verify they pass**
  Run: `npm run test:run`
  Expected output: PASS

- [ ] **Step 5: Commit frontend validateReferences changes**
  Run:
  ```bash
  git add frontend/src/lib/validateReferences.ts frontend/src/lib/validateReferences.test.ts
  git commit -m "feat(normalize): add TS reference normalizers and update existing test cases"
  ```

---

### Task 5: Integrate UI Input Blur Normalization & Auto-Splitting

**Files:**
- Modify: `frontend/src/components/annotation/ReferenceCard.tsx`
- Modify: `frontend/src/components/admin/training/ConceptRowEditor.tsx`

- [ ] **Step 1: Update ReferenceCard.tsx inputs with onBlur handlers**
  Add imports of TS normalizers and attach `onBlur` events to the input fields in [frontend/src/components/annotation/ReferenceCard.tsx](file:///Users/barandincoguz/Desktop/AnnotationProgram/frontend/src/components/annotation/ReferenceCard.tsx):
  ```typescript
  // Import normalizer helpers at line 8
  import { parseComplexMadde, normalizeMadde, normalizeIdentifier, normalizeKanunAdi } from '@/lib/validateReferences'

  // Update inputs:
  // 1. Kanun Adı onBlur (line 177)
  onBlur={(e) => {
    const cleaned = normalizeKanunAdi(e.target.value)
    onChange(set(value, 'kanun_ad', cleaned || ''))
  }}

  // 2. Madde onBlur (line 186)
  onBlur={(e) => {
    const val = e.target.value
    const parsed = parseComplexMadde(val)
    if (parsed) {
      onChange({
        ...value,
        madde: parsed.madde,
        fikra: parsed.fikra || value.fikra,
        bent: parsed.bent || value.bent,
      })
    } else {
      onChange(set(value, 'madde', normalizeMadde(val) || ''))
    }
  }}

  // 3. Fıkra onBlur (line 195)
  onBlur={(e) => {
    const cleaned = normalizeIdentifier(e.target.value)
    onChange(set(value, 'fikra', cleaned || ''))
  }}

  // 4. Bent onBlur (line 204)
  onBlur={(e) => {
    const cleaned = normalizeIdentifier(e.target.value)
    onChange(set(value, 'bent', cleaned || ''))
  }}
  ```

- [ ] **Step 2: Update ConceptRowEditor.tsx inputs with onBlur handlers**
  Modify [frontend/src/components/admin/training/ConceptRowEditor.tsx](file:///Users/barandincoguz/Desktop/AnnotationProgram/frontend/src/components/admin/training/ConceptRowEditor.tsx) to attach identical `onBlur` handlers to input fields:
  ```typescript
  import { Input } from '@/components/ui/input'
  import { Button } from '@/components/ui/button'
  import type { Concept } from '@/lib/adminSchemas'
  import { parseComplexMadde, normalizeMadde, normalizeIdentifier, normalizeKanunAdi } from '@/lib/validateReferences'

  interface Props {
    value: Concept
    onChange: (v: Concept) => void
    onRemove: () => void
  }

  export function ConceptRowEditor({ value, onChange, onRemove }: Props) {
    const set = (k: keyof Concept, v: string | null) => onChange({ ...value, [k]: v })
    return (
      <div className="flex flex-wrap gap-2 rounded border p-2">
        <Input placeholder="kanun_no (zorunlu)" value={value.kanun_no} onChange={(e) => set('kanun_no', e.target.value)} />
        <Input
          placeholder="kanun_ad"
          value={value.kanun_ad ?? ''}
          onChange={(e) => set('kanun_ad', e.target.value || null)}
          onBlur={(e) => set('kanun_ad', normalizeKanunAdi(e.target.value))}
        />
        <Input
          placeholder="madde"
          value={value.madde ?? ''}
          onChange={(e) => set('madde', e.target.value || null)}
          onBlur={(e) => {
            const val = e.target.value
            const parsed = parseComplexMadde(val)
            if (parsed) {
              onChange({
                ...value,
                madde: parsed.madde,
                fikra: parsed.fikra || value.fikra,
                bent: parsed.bent || value.bent,
              })
            } else {
              set('madde', normalizeMadde(val))
            }
          }}
        />
        <Input
          placeholder="fikra"
          value={value.fikra ?? ''}
          onChange={(e) => set('fikra', e.target.value || null)}
          onBlur={(e) => set('fikra', normalizeIdentifier(e.target.value))}
        />
        <Input
          placeholder="bent"
          value={value.bent ?? ''}
          onChange={(e) => set('bent', e.target.value || null)}
          onBlur={(e) => set('bent', normalizeIdentifier(e.target.value))}
        />
        <Button variant="ghost" size="sm" onClick={onRemove}>Kaldır</Button>
      </div>
    )
  }
  ```

- [ ] **Step 3: Write ReferenceCard component-level blur tests**
  Create [frontend/src/components/annotation/ReferenceCard.test.tsx](file:///Users/barandincoguz/Desktop/AnnotationProgram/frontend/src/components/annotation/ReferenceCard.test.tsx) (or append to it if exists) with:
  ```typescript
  import { describe, it, expect, vi } from 'vitest'
  import { render, screen, fireEvent } from '@testing-library/react'
  import { ReferenceCard } from './ReferenceCard'
  import { emptyReferenceItem } from '@/lib/validateReferences'

  describe('ReferenceCard blur auto-splitting and normalization', () => {
    it('splits complex madde value on blur and triggers onChange', () => {
      const onChange = vi.fn()
      const value = emptyReferenceItem()
      
      render(
        <ReferenceCard
          index={0}
          value={value}
          onChange={onChange}
          onRemove={() => {}}
          disabled={false}
          isExpanded={true}
          onExpand={() => {}}
        />
      )

      const maddeInput = screen.getByLabelText('Madde')
      fireEvent.change(maddeInput, { target: { value: '16/1-a' } })
      fireEvent.blur(maddeInput)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          madde: '16',
          fikra: '1',
          bent: 'a',
        })
      )
    })

    it('expands abbreviation for kanun_ad on blur', () => {
      const onChange = vi.fn()
      const value = emptyReferenceItem()

      render(
        <ReferenceCard
          index={0}
          value={value}
          onChange={onChange}
          onRemove={() => {}}
          disabled={false}
          isExpanded={true}
          onExpand={() => {}}
        />
      )

      const kanunAdInput = screen.getByLabelText('Kanun Adı')
      fireEvent.change(kanunAdInput, { target: { value: 'KVK' } })
      fireEvent.blur(kanunAdInput)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          kanun_ad: 'Kurumlar Vergisi Kanunu',
        })
      )
    })
  })
  ```

- [ ] **Step 4: Run all frontend tests and verify they pass**
  Run: `npm run test:run`
  Expected output: PASS

- [ ] **Step 5: Run all backend tests and verify they pass**
  Run: `pytest -q`
  Expected output: PASS

- [ ] **Step 6: Commit all UI integration and test files**
  Run:
  ```bash
  git add frontend/src/components/annotation/ReferenceCard.tsx frontend/src/components/annotation/ReferenceCard.test.tsx frontend/src/components/admin/training/ConceptRowEditor.tsx
  git commit -m "feat(ui): hook up onBlur normalizers to ReferenceCard and ConceptRowEditor inputs"
  ```
