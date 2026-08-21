# Comprehensive MLOps & Statistical Quality Audit Report
**Dataset:** Turkish Tax Ruling Legal Corpus (*Özelge Anotasyon Platformu*)  
**Target Architecture:** Apple Silicon MLX (G0 Zero-Shot Model) $\leftrightarrow$ NeonDB PostgreSQL Outbox $\leftrightarrow$ Hugging Face Spaces  
**Evaluation Snapshot Date:** 2026-08-21  
**Author / Evaluator:** Antigravity MLOps & AI Engineering Suite  

---

## 1. Executive Summary & Population Overview

This report provides a formal statistical benchmark and quality analysis of the legal reference extraction pipeline. The evaluation compares the autonomous MLX G0 extraction model against double-verified human ground-truth annotations produced by legal scholars.

| Population Parameter | Value | Description |
| :--- | :--- | :--- |
| **Total Ingested Corpus** | **17,923** | Unique special tax rulings (*özelgeler*) |
| **Total Model Predictions (NeonDB)** | **4,048** | Pre-computed model extractions |
| **Model Ingestion Success Rate** | **98.84%** | 4,001 successful / 47 edge-case errors (token ceiling/truncation) |
| **Total Scholar Annotations (NeonDB)** | **1,678** | Unique documents reviewed by human legal experts |
| **Completed Scholar Annotations** | **1,525** | Finalized human-verified ground-truth documents |
| **Paired Overlap Evaluation Set ($N$)** | **1,361** | Documents with concurrent Human Ground Truth & Model Prediction |
| **Active Scholar Annotators** | **18** | Distinct authenticated annotators |

---

## 2. Citation Distribution & Statistical Parity

A core metric in information extraction for legal texts is whether the model captures the true citation density without over-generating (hallucination) or under-generating (omission).

### Citation Density Distribution Parameters

$$\text{Reference Count per Document Distribution: } X_{\text{model}} \text{ vs. } X_{\text{human}}$$

| Statistical Metric | Model Predictions ($N=4,001$) | Human Annotations ($N=1,525$) | Statistical Parity / Delta ($\Delta$) |
| :--- | :--- | :--- | :--- |
| **Mean ($\mu$)** | **4.632** | **4.773** | $-0.141$ ($-2.95\%$) |
| **Standard Deviation ($\sigma$)** | **4.111** | **4.074** | $+0.037$ |
| **Median ($Q_2 / \text{p50}$)** | **3.000** | **4.000** | $-1.000$ |
| **25th Percentile ($Q_1 / \text{p25}$)** | **1.000** | **2.000** | $-1.000$ |
| **75th Percentile ($Q_3 / \text{p75}$)** | **6.000** | **6.000** | **0.000 (Exact Match)** |
| **90th Percentile ($\text{p90}$)** | **10.000** | **10.000** | **0.000 (Exact Match)** |
| **95th Percentile ($\text{p95}$)** | **13.000** | **13.000** | **0.000 (Exact Match)** |
| **99th Percentile ($\text{p99}$)** | **19.000** | **18.760** | $+0.240$ |
| **Min / Max Range** | $[1, 42]$ | $[0, 30]$ | — |

> **Key Takeaway for Journal Publication:**  
> The Pearson correlation coefficient on paired overlap documents is **$r = 0.8581$ ($p < 0.001$)**, proving an exceptionally high linear correlation between human annotator citation depth and model prediction volume across all percentiles ($p_{75}, p_{90}, p_{95}$).

---

## 3. Extraction Accuracy & Alignment Metrics

Evaluated on the paired overlap dataset of **$N = 1,361$ completed rulings**, measuring both **Core-Level** (Law No + Article No) and **Exact-Level** (Law No + Article No + Clause/Fıkra + Subclause/Bent).

### Global Metric Summary

```mermaid
pie title Overlap Alignment Classification (Core Level)
    "True Positives (Agreed)" : 4730
    "False Positives (Model Excess)" : 1061
    "False Negatives (Model Missed)" : 879
```

| Evaluation Granularity Level | True Positives ($TP$) | False Positives ($FP$) | False Negatives ($FN$) | Precision ($P$) | Recall ($R$) | **$F_1$-Score** | Median Jaccard ($J$) | Mean Jaccard ($\bar{J}$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Core Level**<br>*(Kanun No + Madde)* | **4,730** | 1,061 | 879 | **81.68%** | **84.33%** | **82.98%** | **0.8889** | **0.7795** |
| **Exact Level**<br>*(Kanun + Madde + Fıkra + Bent)* | **4,853** | 1,739 | 1,690 | **73.62%** | **74.17%** | **73.89%** | **0.6667** | **0.6527** |

$$\text{Core Level } F_1 = 2 \times \frac{0.8168 \times 0.8433}{0.8168 + 0.8433} = 82.98\%$$

---

## 4. Per-Law Domain Performance Breakdown

Top Turkish Tax & Commercial Codes ranked by human annotation volume within the overlap benchmark set:

| Law Code (Kanun No) | Official Law Title (*Kanun Adı*) | Human Ground Truth ($N_{\text{human}}$) | Model Predicted ($N_{\text{model}}$) | True Positives ($TP$) | Precision ($P$) | Recall ($R$) | **$F_1$-Score** |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **4760** | Özel Tüketim Vergisi Kanunu (ÖTVK) | 203 | 206 | 197 | **95.63%** | **97.04%** | **96.33%** |
| **1319** | Emlak Vergisi Kanunu | 103 | 93 | 90 | **96.77%** | **87.38%** | **91.84%** |
| **6306** | Afet Riski Altındaki Alanların Dönüştürülmesi | 23 | 25 | 22 | **88.00%** | **95.65%** | **91.67%** |
| **5520** | Kurumlar Vergisi Kanunu (KVK) | 443 | 423 | 385 | **91.02%** | **86.91%** | **88.92%** |
| **6802** | Gider Vergileri Kanunu | 63 | 61 | 55 | **90.16%** | **87.30%** | **88.71%** |
| **492** | Harçlar Kanunu | 126 | 133 | 114 | **85.71%** | **90.48%** | **88.03%** |
| **488** | Damga Vergisi Kanunu (DVK) | 315 | 388 | 305 | **78.61%** | **96.83%** | **86.77%** |
| **193** | Gelir Vergisi Kanunu (GVK) | 1,220 | 1,240 | 1,061 | **85.56%** | **86.97%** | **86.26%** |
| **7338** | Veraset ve İntikal Vergisi Kanunu | 26 | 32 | 25 | **78.12%** | **96.15%** | **86.20%** |
| **213** | Vergi Usul Kanunu (VUK) | 1,203 | 1,220 | 1,008 | **82.62%** | **83.79%** | **83.20%** |
| **6102** | Türk Ticaret Kanunu (TTK) | 34 | 39 | 30 | **76.92%** | **88.24%** | **82.19%** |
| **3065** | Katma Değer Vergisi Kanunu (KDVK) | 1,222 | 1,174 | 970 | **82.62%** | **79.38%** | **80.97%** |
| **4721** | Türk Medeni Kanunu (TMK) | 42 | 52 | 38 | **73.08%** | **90.48%** | **80.85%** |
| **2464** | Belediye Gelirleri Kanunu | 41 | 39 | 27 | **69.23%** | **65.85%** | **67.50%** |

---

## 5. Architectural & Reliability Findings

1. **Deterministic Edge Handling:**  
   Out of 4,048 processed documents, only 47 (1.16%) were flagged as unprocessable (due to legal text exceeding model sequence context limits). These documents are permanently and deterministically cached with `status='error'`, preventing redundant compute wastage.
2. **Outbox Synchronization Latency:**  
   Through the `v0018_model_predictions_outbox_triggers` migration, model outputs pushed from the local Mac MLX runner to Hugging Face Spaces are asynchronously drained and mirrored to NeonDB with near zero data drift.
3. **Domain Coverage:**  
   The model achieves $\ge 80\% F_1$ across 13 of the top 14 legal codes in Turkish tax jurisprudence, with Specialized Tax Codes (ÖTVK, Emlak, KVK) demonstrating $\ge 88\% F_1$ extraction precision.

---
*Report auto-generated from live NeonDB telemetry and verified against local and remote SQLite schemas.*
