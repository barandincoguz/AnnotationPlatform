# Domain Context & Canonical Glossary

This document defines the canonical domain language and concepts for the Turkish Tax Ruling Annotation Platform (*Özelge Anotasyon Platformu*) and the autonomous Quality Audit MLOps suite.

---

## 1. Core Domain Entities

### Özelge (Special Tax Ruling)
An official administrative interpretation issued by the Turkish Revenue Administration (*Gelir İdaresi Başkanlığı - GİB*) answering specific taxpayer tax liability inquiries. Rulings contain unstructured statutory analyses citing tax codes, articles, paragraphs, and clauses.

### Statutory Reference (Kanun Referansı)
A discrete citation pointing to an enacted legal statute. Modeled as a structured tuple:
- `kanun_no`: Official numeric Law Code (e.g., `193` for GVK, `3065` for KDVK, `213` for VUK).
- `kanun_ad`: Formal statutory title (e.g., `Gelir Vergisi Kanunu`).
- `madde`: Article designation (e.g., `94`, `geçici 67`).
- `fikra`: Clause / paragraph identifier (numeric string or empty).
- `bent`: Subclause identifier (alphabetic string or empty).
- `source_text`: Exact verbatim quotation from the ruling text where the citation occurs.

### Core Reference (Çekirdek Referans)
The primary tuple key `(kanun_no, madde)`. Evaluates statutory presence regardless of clause-level granularity.

### Exact Reference (Tam / Ayrıntılı Referans)
The full 4-tuple key `(kanun_no, madde, fikra, bent)`. Represents strict subclause-level citation accuracy.

---

## 2. Quality Audit & Pre-Submit Workflow

### Pre-Audit Comparison (Ön-Denetim Karşılaştırması)
An on-demand verification endpoint (`POST /api/annotations/{document_id}/pre-audit`) executed before a human annotator finalizes an annotation. Compares human references against pre-computed model references.

### Discrepancy Categorization
- `model_only`: The model extracted a valid reference that the human annotator omitted.
- `human_only`: The human annotator extracted a reference that the model missed.
- `detail_mismatch`: Both extracted the same Core Reference `(kanun_no, madde)` but disagree on `fikra` or `bent`.

### Audit Decision Buckets
- `GREEN`: Zero discrepancies or high similarity ($J \ge 0.85$). Safe for immediate single-click completion.
- `YELLOW`: Minor detail mismatch or single omission. Requires user acknowledgment or 1-click addition.
- `RED`: Major statutory mismatch or contradictory core laws. Requires explicit human override with mandatory justification.

---

## 3. Production & MLOps Infrastructure

### Outbox Mirror Pattern
A transactional outbox architecture ensuring that local SQLite mutations in the cloud container (Hugging Face Spaces) are reliably captured via SQLite triggers (`_outbox`) and asynchronously delivered to remote Neon PostgreSQL (`baran_*` tables).

### Sealed Model Registry (G0)
A cryptographically pinned model definition artifact (`G0.json`) specifying model snapshot SHA, LoRA adapter SHA256 checksum, tokenizer configuration, and pinned context windows.

