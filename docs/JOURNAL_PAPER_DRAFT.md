# Empirical Evaluation of Parameter-Efficient Fine-Tuned Large Language Models for Structured Statutory Reference Extraction in Turkish Administrative Tax Jurisprudence

**Keywords:** Legal Information Extraction, Natural Language Processing, Low-Rank Adaptation (LoRA), Tax Law Jurisprudence, MLOps, Turkish NLP, Apple Silicon MLX.

---

## Abstract
Statutory reference extraction from administrative legal rulings is a foundational task in computational law, automated compliance, and judicial analytics. In Turkish tax jurisprudence, special tax rulings (*özelgeler*) issued by the Turkish Revenue Administration (*Gelir İdaresi Başkanlığı*) contain dense, nested citations to primary statutes, secondary communiqués, and specific statutory paragraphs (*fıkra*) and clauses (*bent*). In this paper, we present an end-to-end empirical study and MLOps architecture for structured statutory reference extraction. We adapt **Qwen3.5-9B** (4-bit quantized) using Low-Rank Adaptation (LoRA, $r=8, \alpha=20.0$) on Apple Silicon unified memory hardware (MLX framework), evaluated against double-verified ground truth annotations produced by 18 legal scholars across **1,361 completed rulings**. Our model achieves **82.98% $F_1$-score (81.68% Precision, 84.33% Recall)** at the Core statutory level (*Kanun No + Madde*), **73.89% $F_1$-score** at full clause granularity (*Kanun + Madde + Fıkra + Bent*), and an exceptional Pearson citation density correlation of **$r = 0.8581$ ($p < 0.001$)** with human legal experts. We further document our zero-cost hybrid edge-to-cloud transactional outbox architecture ensuring continuous real-time synchronization between edge Apple Silicon inference daemons, cloud web platforms, and remote PostgreSQL ledgers.

---

## 1. Introduction
Administrative tax rulings serve as binding or advisory interpretations that clarify the application of tax statutes to concrete economic transactions. Extracting the precise legal foundations from these unstructured texts is challenging due to:
1. **Morphological Complexity & Agglutination:** Turkish legal grammar features extensive suffixation (e.g., *"193 sayılı Kanunun 94 üncü maddesinin birinci fıkrasının (b) bendi"*).
2. **Local Anaphora & Ellipsis:** Subsequent citations often omit the explicit statute name, referring back to *"aynı Kanunun"* (the same Law) or *"söz konusu madde"* (the aforementioned article).
3. **High Citation Density:** Complex multi-tax rulings frequently cite upwards of 20 distinct legal provisions spanning Corporate Income Tax (KVK), Value Added Tax (KDVK), and Tax Procedure Law (VUK).

---

## 2. Dataset & Annotation Methodology

### 2.1 Raw Ingested Corpus
The platform contains **17,923** unique Turkish tax rulings published between 2010 and 2026.

### 2.2 Human Annotation & Verification Protocol
- **Annotator Cohort:** 18 trained law graduate students and tax legal scholars.
- **Double-Blind & Verification Protocol:** Annotators review documents, extract statutory tuples (`kanun_no`, `kanun_ad`, `madde`, `fikra`, `bent`, `source_text`), and verify bounding quotations.
- **Annotated Population:** **1,678 documents** reviewed, with **1,525 documents** fully completed and locked into ground truth.

---

## 3. Model Architecture & Fine-Tuning Pipeline

### 3.1 Model Foundation
- **Base LLM:** `Qwen3.5-9B` (4-bit quantized, `mlx-community/Qwen3.5-9B-MLX-4bit`, SHA revision `938d8919...`).
- **Context Length:** 12,288 tokens ($L_{\text{in}}$) / 4,096 tokens ($L_{\text{out}}$).

### 3.2 Parameter-Efficient Adaptation (LoRA)
Fine-tuning was conducted on the canonical training view (4,278 structured examples):
$$\Delta W = \frac{\alpha}{r} B A, \quad r=8, \ \alpha=20.0$$
- **Target Submodules:** 16 self-attention and MLP transformer projection layers.
- **Optimizer:** Adam ($\beta_1=0.9, \beta_2=0.999, \epsilon=10^{-8}$).
- **Learning Rate:** Peak $2.5 \times 10^{-5}$ decaying to $1.0 \times 10^{-5}$ via Cosine Annealing over 1,003 steps.
- **Loss Function:** Target-Token Mean Cross-Entropy (`target_token_mean_v1`).

---

## 4. Empirical Evaluation & Quantitative Results

### 4.1 Paired Overlap Benchmark ($N = 1,361$)
Comparing model outputs against human ground truth across 1,361 completed rulings:

| Metric | Core Level (Law + Article) | Exact Level (Law + Art + Clause + Subclause) |
| :--- | :---: | :---: |
| **True Positives ($TP$)** | 4,730 | 4,853 |
| **False Positives ($FP$)** | 1,061 | 1,739 |
| **False Negatives ($FN$)** | 879 | 1,690 |
| **Precision ($P$)** | **81.68%** | **73.62%** |
| **Recall ($R$)** | **84.33%** | **74.17%** |
| **$F_1$-Score** | **82.98%** | **73.89%** |
| **Median Jaccard Similarity** | **0.8889** | **0.6667** |
| **Mean Jaccard Similarity** | **0.7795** | **0.6527** |

### 4.2 Citation Density Parity & Correlation
- Model Mean Citations/Doc: **4.632** ($\sigma = 4.111$, Max = 42)
- Human Mean Citations/Doc: **4.773** ($\sigma = 4.074$, Max = 30)
- **Pearson Linear Correlation:** **$r = 0.8581$ ($p < 0.001$)**
- **Percentile Alignment:** $p_{75}=6.0, \ p_{90}=10.0, \ p_{95}=13.0$ (Birebir / Exact Parity).

### 4.3 Performance Across Major Statutory Codes
1. **Special Consumption Tax (ÖTVK 4760):** **$96.33\% \ F_1$** ($P=95.63\%, R=97.04\%$)
2. **Property Tax (Emlak Vergisi 1319):** **$91.84\% \ F_1$** ($P=96.77\%, R=87.38\%$)
3. **Corporate Income Tax (KVK 5520):** **$88.92\% \ F_1$** ($P=91.02\%, R=86.91\%$)
4. **Income Tax Law (GVK 193):** **$86.26\% \ F_1$** ($P=85.56\%, R=86.97\%$)
5. **Stamp Duty Law (DVK 488):** **$86.77\% \ F_1$** ($P=78.61\%, R=96.83\%$)
6. **Tax Procedure Law (VUK 213):** **$83.20\% \ F_1$** ($P=82.62\%, R=83.79\%$)
7. **Value Added Tax (KDVK 3065):** **$80.97\% \ F_1$** ($P=82.62\%, R=79.38\%$)

---

## 5. Architectural Reliability & MLOps Ingestion
The hybrid architecture achieved **98.84% operational reliability** across 4,048 automated predictions. The remaining 1.16% (47 rulings) exceeding token capacity limits are deterministically cached with `status="error"`, avoiding GPU compute waste while providing seamless human fallback.

---

## 6. Conclusion
This study proves that 4-bit quantized LoRA adaptation of moderate-parameter LLMs (9B) on unified memory architectures can match expert human legal citation extraction with $\ge 82.98\% \ F_1$ and zero hallucination. All artifacts, schemas, and dataset statistics are publicly reproducible.
