<!-- TITLE -->
Placeholder Title For Pipeline Test

<!-- AUTHORS -->
Author Name
dept. name, institution
City, Country
email

<!-- ABSTRACT -->
Placeholder abstract sentence one. Placeholder abstract sentence two.

<!-- KEYWORDS -->
annotation quality, large language models, legal NLP

<!-- H1: Introduction -->
Placeholder introduction body paragraph.

<!-- FIGURE -->
Cross-check mechanism: the annotator's completed extraction and the model's independent extraction are aligned and routed into four outcome buckets.

<!-- TABLE -->
Model and training configuration
| Parameter | Value |
| Base model | Qwen3.5-9B, 4-bit quantized MLX weights |
| Adaptation | LoRA, r = 8, last 16 layers, scale 20.0, dropout 0.0 |
| Optimizer | AdamW, effective batch 4 (micro-batch 1, accumulation 4) |
| Learning rate | peak 2.5e-5, 42 warmup steps, cosine decay to 1.0e-5 |
| Loss | completion-only cross-entropy, prompt masked |
| Context | 1536 tokens training (256 overlap), 12288 inference |
| Training set | 494 adjudicated documents, 4278 windows, 1003 updates |
| Hardware | Apple Mac Studio, unified memory, Metal |

<!-- TABLE -->
Extraction results. The two rows are different models evaluated against different reference standards and are not directly comparable.
| Evaluation set | Reference standard | F1 | Precision | Recall | Exact-document |
| Sealed test, 50 docs (development configuration) | adjudicated ground truth | 0.789 | 0.861 | 0.728 | 13/50 |
| External, 100 docs (deployed configuration) | single human annotator | 0.805 | 0.8525 | 0.7625 | 47/100 |

<!-- TABLE -->
Routing outcome on the 1294-document batch
| Bucket | Documents | Share | Action |
| GREEN — concordant | 342 | 26.4% | cleared, no expert review |
| YELLOW — minor divergence | 211 | 16.3% | expert review |
| RED — divergence | 738 | 57.0% | expert review |
| QUARANTINE — malformed | 3 | 0.2% | held for handling |
| Total | 1294 | 100% | |

<!-- H1: Conclusion -->
Placeholder conclusion body paragraph.

<!-- REFERENCES -->
A. Author, "Placeholder reference title," in Proc. Some Conf., 2020.
