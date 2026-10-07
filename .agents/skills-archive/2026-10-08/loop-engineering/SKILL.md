---
name: loop-engineering
description: >-
  Use this skill whenever executing continuous, iterative feedback loops (Plan -> Execute -> Audit -> Refine -> Validate)
  for complex software tasks, weekly progress reports, experimental benchmarking, or manuscript writing.
---

# Loop Engineering Skill — Continuous Iterative Engineering & Refinement

This skill provides a systematic framework for conducting continuous engineering and refinement loops to achieve zero-defect, highly verified deliverables.

## The 5-Phase Loop Framework

```
  ┌──────────────┐
  │  1. PLAN     │◄─────────────────────────────────────┐
  └──────┬───────┘                                      │
         │                                              │
  ┌──────▼───────┐                                      │
  │  2. EXECUTE  │                                      │
  └──────┬───────┘                                      │
         │                                              │
  ┌──────▼───────┐      ┌──────────────┐       ┌────────┴───────┐
  │  3. AUDIT    ├─────►│ 4. REFINE    ├──────►│ 5. VALIDATE   │
  └──────────────┘      └──────────────┘       └────────────────┘
```

### Phase 1: Plan & Baseline Scope
- Define explicit quantitative and qualitative targets.
- Inspect all underlying source data, code signatures, and existing documentation before taking action.

### Phase 2: Execute Surgical Modifications
- Apply minimal, precise edits (surgical operations).
- Avoid unnecessary modifications or collateral changes to frozen artifacts (e.g. `conference-preparation/`).

### Phase 3: Audit & Inspect Empirical Logs
- Immediately fetch log files, JSON benchmark outputs, and test outputs.
- Verify byte sizes, line counts, SHA256 hashes, and error messages empirically.

### Phase 4: Refine & Re-run Iterations
- Resolve identified edge cases or discrepancies.
- If a verification gate fails, perform root-cause analysis and re-run the loop until 100% clean pass is achieved.

### Phase 5: Final Validation & Provenance Locking
- Lock verified outputs in `input_artifacts.lock.json` or project ledgers.
- Document all provenance details for future AI agents and human collaborators.
