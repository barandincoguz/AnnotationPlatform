# Standard Operating Guidelines: Turkish Statutory Reference Annotation & Quality Auditing

**Target Domain:** Turkish Tax & Administrative Law (*Türk Vergi ve İdare Hukuku*)  
**Version:** 1.0 (Canonical Gold Standard Specification)  
**Applicability:** Human Legal Scholars, LLM Prompts, Validation Frameworks  

---

## 1. Statutory Reference Tuple Fields & Canonical Formatting

Every legal reference in a tax ruling (*özelge*) must conform to the 6-field canonical tuple schema:

| Field Name | Type | Canonical Format | Examples / Valid Values | Invalid / Anti-Patterns |
| :--- | :---: | :--- | :--- | :--- |
| `kanun_no` | string | Numeric statutory code | `"193"`, `"3065"`, `"213"`, `"5520"`, `"488"` | `"193 sayılı"`, `"GVK"`, `"Kanun 213"` |
| `kanun_ad` | string | Official formal title of the statute | `"Gelir Vergisi Kanunu"`, `"Vergi Usul Kanunu"` | `"Gelir Vergisi"`, `"kdv kanunu"`, `""` |
| `madde` | string | Article designation | `"94"`, `"geçici 67"`, `"mükerrer 298"`, `"ek 1"` | `"Madde 94"`, `"94. madde"`, `"m.94"` |
| `fikra` | string | Clause / Paragraph (numeric only) | `"1"`, `"2"`, `"3"`, `""` (if not specified) | `"1. fıkra"`, `"birinci"`, `"(1)"` |
| `bent` | string | Subclause (alphabetic character only) | `"a"`, `"b"`, `"c"`, `"ç"`, `""` (if not specified) | `"(a)"`, `"a bendi"`, `"a)"` |
| `source_text` | string | Verbatim exact excerpt from ruling text | `"193 sayılı Kanunun 94 üncü maddesi"` | Fabricated or summarized text |

---

## 2. Special Legal Provisions & Edge-Case Rules

### 2.1 Temporary & Duplicate Articles (*Geçici ve Mükerrer Maddeler*)
- **Geçici Madde (Temporary Article):** Must be formatted as `madde="geçici 67"`, `madde="geçici 2"`.
- **Mükerrer Madde (Duplicate Article):** Must be formatted as `madde="mükerrer 298"`, `madde="mükerrer 257"`.
- **Ek Madde (Additional Article):** Must be formatted as `madde="ek 1"`, `madde="ek 2"`.

### 2.2 Secondary Legislation & Communiqués (*Tebliğler ve Yönetmelikler*)
- **General Communiqués (*Genel Tebliğler*):** Do not assign a generic law number if the text refers strictly to a communique article.
- **Parent Statute Reference in a Communiqué:** If the text cites *"X sayılı Kanunun Y maddesinin uygulanmasına ilişkin Tebliğ..."*, extract Law `X` Article `Y`.

### 2.3 Resolving Anaphoric Expressions (*Atıf ve Göndermeler*)
- When text states *"aynı Kanunun 10 uncu maddesi"* or *"söz konusu Kanunun 94 üncü maddesi"*, resolve the pronoun to the antecedent statute cited immediately beforehand in the same section.
- Never emit a reference with empty `kanun_no` when the context allows local statutory resolution.

### 2.4 Tables, Schedules, and Tariff Lists (*Tarife, Cetvel ve Listeler*)
- Attached tax schedules (e.g. *Damga Vergisi (1) sayılı tablo*, *ÖTV (II) sayılı liste*) must be preserved under the parent statute (e.g., `kanun_no="488"`, `madde="1 sayılı tablo"` or `madde="ek 1"`).

---

## 3. Human Pre-Audit Decision Protocol

When an annotator clicks **"Model ile Karşılaştır"** or submits an annotation:
1. **GREEN Bucket ($J \ge 0.85$ or 0 discrepancies):** Review and confirm in 1 click.
2. **YELLOW Bucket (Detail Mismatch / Single Omission):**
   - If model caught a real statutory citation, click **"Model Önerisini Listeme Ekle"**.
   - If model extracted a secondary regulation inappropriately, maintain human ground truth.
3. **RED Bucket (Core Discrepancy):**
   - Provide mandatory justification before completing the override.

