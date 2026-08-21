# ADR 0002: Deterministic Error Caching for Sequence Ceiling Violations

## Status
Accepted

## Context
A small fraction (1.16%) of special tax rulings contain extraordinarily long administrative transcripts, exceeding the pinned 12,288 token context window. In a naive pipeline, these documents trigger unhandled exceptions, causing background agents to retry them infinitely and waste GPU cycles.

## Decision
Documents that exceed the pinned sequence length are treated as deterministic properties of the document rather than transient environment errors:
1. The model marks the result with `status="error"`, `references=[]`, and an explicit error explanation (e.g. `input_token_count exceeds pinned max_sequence_length=12288`).
2. The platform persists this error state in `model_predictions`.
3. When an annotator opens the document, the UI displays *"Bu doküman için model kontrolü yapılamadı"* and allows standard manual annotation without waiting or hanging.

## Consequences
### Positive
- Eliminates infinite retry loops and GPU compute waste.
- Complete deterministic reproducibility: same text produces the exact same failure record.
- Clear, graceful UI feedback for human annotators.
