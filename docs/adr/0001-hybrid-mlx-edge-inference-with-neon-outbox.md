# ADR 0001: Hybrid Apple Silicon MLX Edge Inference with Remote NeonDB Outbox Mirror

## Status
Accepted

## Context
Running continuous LLM inference for 17,923 legal rulings on cloud GPUs is cost-prohibitive and introduces heavy cloud cold-start latencies. Meanwhile, local Apple Silicon hardware (M-series unified memory) provides high-throughput MLX acceleration (~25 tps) without cloud compute fees. However, multiple legal annotators access the system concurrently via a cloud web interface hosted on Hugging Face Spaces (CPU container).

## Decision
We adopted a decoupled, outbound-pull hybrid architecture:
1. **Inference Tier (Local):** An autonomous `predict-agent` daemon runs locally on Apple Silicon, requesting batches of 4 unpredicted documents from Hugging Face Spaces via HTTPS, running G0 inference locally, and pushing structured predictions back to HF Spaces.
2. **Web & Queue Tier (HF Spaces):** Hugging Face Spaces hosts the FastAPI/React application, serving annotator UIs and maintaining local SQLite WAL storage.
3. **Outbox Synchronization (NeonDB):** SQLite database triggers (`_outbox`) intercept every prediction insert and mirror it asynchronously to a shared remote Neon PostgreSQL database (`baran_model_predictions`).

## Consequences
### Positive
- Zero cloud GPU costs ($0 GPU compute bill).
- Full fault tolerance: If the local machine sleeps or is disconnected, cloud annotators continue annotating normally from cached NeonDB predictions.
- High throughput on Apple Silicon MLX.

### Negative
- Local daemon must be running to process unpredicted documents in real time.
- Requires network connectivity between local runner, Hugging Face, and NeonDB.
