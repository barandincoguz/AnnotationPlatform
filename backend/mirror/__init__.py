"""Phase 4 dual-write mirror: outbox dispatcher + Neon client + admin health.

Public surface:
  - backend.mirror.config: NEON_MIRROR_URL, NEON_MIRROR_BATCH_SIZE, etc.
  - backend.mirror.neon_client: NeonClient, NeonTransient, NeonPermanent.
  - backend.mirror.dispatcher: run_dispatcher, start, stop.
  - backend.mirror.health: collect_health.
"""
