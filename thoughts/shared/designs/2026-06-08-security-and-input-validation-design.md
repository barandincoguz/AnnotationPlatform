<frontmatter>
date: 2026-06-08
topic: "Security and Input Validation"
status: validated
</frontmatter>

## Problem Statement

Our annotation platform requires robust security measures and clean, high-quality reference data. Currently, several security vulnerabilities and input validation gaps exist:

**Security Vulnerabilities:**
- **Secret Strength:** The production secret enforcement lacks entropy validation, allowing weak or repetitive secrets.
- **CSRF Origin Matching:** Case-sensitivity and port mismatches in CSRF checking can block legitimate requests or allow bypasses.
- **Rate Limiter Memory Leak:** In-memory rate limiting lacks a mechanism to clean up stale IP keys, risking memory exhaustion.
- **Unsalted IP Hashes:** IP addresses are hashed using unsalted SHA-256, leaving them vulnerable to rainbow table brute-force recovery.
- **Audit Log Integrity:** Synchronous DB writes block the event loop, and admin audit logs lack tamper-evident integrity checks.

**Input Validation Gaps:**
- **Bent Field Noise:** Users frequently enter bent values with parentheses or dots (e.g., `(a)`, `a.`, `(a).`), which are stored without normalization.
- **Complex Madde Inputs:** Users enter combined values like `5/1-a` (meaning Article 5, Paragraph 1, Clause a) directly into the `madde` field, causing database pollution and breaking search filters.

This design addresses these issues by strengthening core security components and introducing smart, automatic input normalization and parsing.

---

## Constraints

To ensure a safe and seamless rollout, the design must respect the following constraints:
- **No Schema Breaking Changes:** We must preserve the existing database schemas and API contracts for references.
- **Consistent Normalization:** Validation and cleaning rules must be identical across both the frontend and backend.
- **Non-Production Compatibility:** Security enforcements must not break developer environments or automated test suites.
- **Zero Code Execution:** This phase is design-only; no implementation code must be written or executed directly in this step.

---

## Approach

We will implement a two-pronged approach to address security and input quality:

**1. Security Hardening:**
- **Shannon Entropy:** Introduce a minimum entropy check for production session secrets.
- **Origin Normalization:** Lowercase and normalize ports for all CSRF origin matching.
- **Garbage Collection:** Add a thread-safe background task to periodically evict inactive IP keys from the rate limiter.
- **Salted IP Hashing:** Transition `hash_ip` to use HMAC-SHA256 with a secure pepper/salt.
- **Async & Tamper-Evident Logging:** Move audit logging to an asynchronous queue and implement cryptographic hash-chaining for admin logs.

**2. Smart Input Normalization & Auto-Splitting (Chosen Approach):**
- **Bent Cleaning:** Automatically strip parentheses, dots, quotes, and convert to lowercase on both frontend (blur) and backend (clean).
- **Smart Auto-Splitting:** When a user types a complex reference like `5/1-a` in the `madde` field, the system will automatically parse it using a regex pattern and split it into `madde: "5"`, `fikra: "1"`, and `bent: "a"`.
- **Strict Fallback Validation:** If a user enters an invalid complex format that cannot be parsed, a validation error will block submission on both the frontend and backend.

*Alternative considered:* We considered strictly blocking `5/1-a` without auto-splitting. We rejected this because it frustrates users who copy-paste references, whereas auto-splitting provides an optimal, frictionless user experience.

---

## Architecture

The system's components are divided between the security middleware layer and the reference input processing pipelines:

```
[ User Input: "5/1-a" ] ──► [ ReferenceCard (Frontend) ] ──► [ validateReferences.ts (Regex Splitting) ]
                                                                     │ (Auto-populates fields)
                                                                     ▼
[ Saved Reference ] ◄── [ diff.py (Backend Cleaning) ] ◄── [ models.py (Pydantic Format Check) ]
```

**Security Pipeline:**
```
[ HTTP Request ] ──► [ OriginCheckMiddleware ] ──► [ RateLimiter ] ──► [ Auth & Controller ] ──► [ Async Audit Queue ]
```

---

## Components

### 1. Frontend Reference Components
- **`ReferenceCard.tsx`:** Listens to the `onBlur` event of the `madde` input. If a complex pattern is detected, it triggers the splitting utility and updates the form state.
- **`validateReferences.ts`:** Houses the regex parsing logic and validates that fields do not contain illegal characters.

### 2. Backend Reference Utilities
- **`models.py`:** Updates the `ReferenceItem` Pydantic model with a validator on `madde` to reject unparsed complex formats.
- **`diff.py`:** Enhances the `_clean` function to strip parentheses, dots, and normalize case for the `bent` field.

### 3. Security Middleware
- **`prod_enforce.py`:** Adds Shannon entropy calculation for session secrets.
- **`csrf.py`:** Adds origin normalization helper.
- **`rate_limit.py`:** Launches a background thread/task to clean up stale deques.
- **`auth.py`:** Updates `hash_ip` to use a salted HMAC-SHA256.
- **`audit.py`:** Implements an async logging queue and hash-chaining logic for admin audit records.

---

## Data Flow

### Reference Normalization and Auto-Splitting Flow:
1. **Input Capture:** The user types or pastes `5/1-a` into the `Madde` input field on the frontend.
2. **On-Blur Trigger:** When the user clicks away, the `onBlur` event triggers the regex analyzer.
3. **Regex Matching:** The string is matched against `^(\d+)(?:\/(\d+))?(?:-([a-zA-ZçğıöşüÇĞİÖŞÜ]))?$`.
4. **State Update:**
   - `madde` is updated to `"5"`.
   - `fikra` is updated to `"1"`.
   - `bent` is updated to `"a"`.
5. **Bent Cleaning:** The `bent` field is passed through the cleaning function, converting `"(a)"` or `"a."` to `"a"`.
6. **API Submission:** The form is submitted to the backend.
7. **Pydantic Validation:** The backend validates that `madde` is a clean number/string without slashes or dashes.
8. **Deduplication & Save:** The backend normalizes, deduplicates, and commits the reference to the database.

---

## Error Handling

- **Invalid Complex Formats:** If a user enters an unparseable format like `5/1/a-b` into the `madde` field, the frontend displays an inline validation message: *"Geçersiz format. Lütfen Madde, Fıkra ve Bent alanlarını ayrı ayrı doldurun."*
- **Backend Rejection:** If the frontend validation is bypassed, the backend Pydantic model raises a `ValueError` for invalid `madde` formats, returning a `422 Unprocessable Entity` status code.
- **Weak Secrets:** If the production environment is configured with a low-entropy or placeholder secret, the application fails to start up during `enforce_production_secrets` with a descriptive configuration error.

---

## Testing Strategy

- **Unit Tests for Normalization:**
  - Verify that `(a)`, `a.`, `A`, and `(a).` are all cleaned to `"a"`.
  - Verify that `5/1-a` is parsed correctly into `madde: "5"`, `fikra: "1"`, `bent: "a"`.
  - Verify that invalid formats like `5/1/a-b` fail validation.
- **Integration Tests for Security:**
  - Verify that low-entropy keys fail production startup.
  - Test that the rate limiter garbage collection thread successfully removes expired keys.
  - Verify that salted IP hashes are unique and resistant to simple dictionary lookups.
- **End-to-End Tests:**
  - Simulate a user pasting `5/1-a` into the UI and verify that all three fields populate correctly.

---

## Open Questions

- **Roman Numerals:** Should we support Roman numerals in the madde/fıkra fields (e.g., `V/1-a`)? 
  *Decision:* Yes, our regex pattern `[a-zA-ZçğıöşüÇĞİÖŞÜ]` naturally handles Roman numerals as strings, so they are fully supported without extra complexity.
