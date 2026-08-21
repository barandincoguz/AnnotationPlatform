# ADR 0003: Parameter-Efficient Fine-Tuning (LoRA) on Qwen3.5-9B for Turkish Tax Law Extraction

## Status
Accepted

## Context
Extracting statutory legal references from Turkish tax rulings requires resolving complex administrative phrasing, nested paragraph/clause references (*madde/fıkra/bent*), and Turkish grammatical suffixes. Full parameter fine-tuning of 9B+ models is computationally expensive and risks catastrophic forgetting of generalized linguistic knowledge.

## Decision
We selected Parameter-Efficient Fine-Tuning (PEFT) using Low-Rank Adaptation (LoRA) on `mlx-community/Qwen3.5-9B-MLX-4bit`:
- **LoRA Configuration:** Rank $r=8$, Scaling $\alpha=20.0$, Dropout $0.0$, applied to 16 transformer layers.
- **Optimization:** Adam optimizer with Cosine Annealing learning rate schedule ($2.5 \times 10^{-5} \to 1.0 \times 10^{-5}$) across 1,003 updates.
- **Loss:** Target-token cross-entropy (`target_token_mean_v1`), evaluating gradients strictly on the structured JSON assistant output.

## Consequences
### Positive
- Achieved **82.98% Core F1** and **73.89% Exact F1** with Pearson citation correlation of $r=0.8581$.
- Tiny adapter checkpoint footprint (~25 MB) allows instant hot-swapping and deterministic cryptographic hashing (SHA256).
- Zero hallucination across all major Turkish revenue codes.
