# IISEC 2027 Conference Paper — Design Spec

**Date:** 2026-08-17
**Deliverable:** A 6-page IEEE-format conference paper for IISEC 2027, describing the LLM cross-check
mechanism added to the tax-ruling annotation platform.
**Status:** design approved in brainstorming; awaiting user review of this spec before the writing plan.

---

## 1. Venue constraints (verified)

| Item | Value | Source |
| --- | --- | --- |
| Conference | IISEC 2027 — 6th IEEE International Informatics and Software Engineering Conference | `iisec.tbdakademi.org.tr/2027/`, `easychair.org/cfp/IISEC2027` |
| Dates / place | 28–30 January 2027, Ankara, Turkey (hybrid) | same |
| Submission deadline | **29 November 2026** | same |
| Notification / camera-ready | 31 December 2026 / 17 January 2027 | same |
| Page limit | **6 pages maximum** | official submission page |
| References inside limit? | Not stated — **assume yes** | — |
| Format | IEEE conference template, A4 | `template-a4.docx`, identical to local `iisec_template.docx` |
| Language | English | template is English-only |
| System | EasyChair | official pages |
| Review | "at least two scientific committee members"; blind status **not stated** → assume **not** double-blind | official pages |
| Indexing | submitted for possible IEEE Xplore inclusion (conditional) | official pages |
| Best-fit topics | "Software Quality Assurance", "Artificial Intelligence", "Machine Learning" | `2027/main-topics` |

Co-sponsors include TED University. IISEC 2026's theme was "Large Language Models in Software
Engineering"; the 2027 CFP foregrounds generative AI — the paper is on-theme.

## 2. Single contribution claim

> We integrated a locally fine-tuned open-weight LLM into an expert legal-annotation platform as an
> **independent second extractor**. It produces the same structured citation schema as the human
> annotator, and a router compares the two extractions to classify each document as concordant or
> in need of expert review. On a 1,294-document production batch, 342 documents (26.4%) were
> classified as fully concordant and cleared automatically, reducing the documents requiring expert
> review to 949 — a **26.4% reduction in expert review load**.

One contribution. Nothing else.

Baseline for the reduction: without the mechanism, an expert verifying this batch must examine all
1,294 documents. Do **not** use the 1,180 → 949 / −19.58% framing — that compares two internal
router configurations and would require describing the target policy that the user has excluded from
the paper (see §3).

## 3. Explicitly out of scope

Do **not** introduce any of the following, even in passing, beyond at most a single clause:

- the offline annotation-quality harness and its 17-rule rubric (R01–R17)
- the 979 → 9 R07 false-positive collapse
- the n=400 sample audit (~18% claimed vs 0.5% verified)
- inter-annotator Jaccard agreement (0.679, n=12)
- gamification, XP, badges, `review_kept`
- the SQLite→Neon CDC mirror, outbox triggers, backup-to-GitHub
- document locking, SSE, the training/quiz onboarding gate
- cross-team coordination with the partner team
- per-annotator performance rankings (ethically and scientifically inadvisable at these sample sizes)
- **the VUK 213/413 target policy and its before/after effect** (user decision, 2026-08-17). All
  reported figures are the post-policy values. The pre-policy bucket counts (GREEN 111, YELLOW 93,
  RED 1,087) and the 231-document RED→GREEN transition are recorded here for internal traceability
  only and must not appear in the paper.

Rationale: the user asked for one simple story. Every one of these opens a question the paper cannot
answer in 6 pages.

## 4. Claim discipline (non-negotiable)

The user selected the **zero-extra-work** option. Therefore:

1. **Measured and claimable:** concordance counts, bucket transitions, review-load reduction,
   extraction metrics on the two evaluation sets, latency, hardware footprint.
2. **NOT claimable:** that the mechanism reduced annotator error, improved annotator behaviour, or
   "kept annotators on track." No before/after annotator error rate exists. "Keeping annotators
   aligned" may appear only as the **design intent / deployment purpose**, never as a result.
   Behavioural impact is stated as future work.
3. **Terminology, enforced throughout:**
   - Metrics on the canonical sealed Test-50 (multi-rater adjudicated GT v3) → *ground-truth F1 /
     extraction accuracy*.
   - Metrics on External-100 (single human annotator labels as reference) → **human-annotator
     agreement**, never "accuracy". State the reason in one sentence.
4. **Two distinct models must not be conflated.** F1 0.789 belongs to the *development*
   configuration (394 training documents, cosine-150 schedule, best checkpoint at update 75). The
   *deployed* model is an all-data refit over all 494 canonical documents with a cosine-1003
   schedule. They differ in both training data and number of optimizer updates (75 vs 1003).
   Required framing: the sealed-test result establishes that the approach generalizes to unseen
   documents; the deployed model's behaviour is characterized by External-100 agreement and the
   1,294-document routing outcome. No unseen-canonical estimate exists for the deployed model —
   say so.
5. **Disclose selection-on-test.** External-100 was used both to select the operational checkpoint
   (update 550 vs update 1003) and to report the 0.805 agreement figure. One sentence: the reported
   figure is therefore not an unbiased estimate of agreement on new documents.
6. **The in-UI warning surface is described as part of the deployed system** (user decision,
   2026-08-18). It was not live when the paper was drafted; the user's instruction is to write
   it as deployed because it is being added. §IV-E therefore uses the present tense.
   **Pre-submission check, retained deliberately:** confirm the warning surface is actually
   live before submitting on 2026-11-29, or change the tense. This serves the user's own
   stated intent — without the check nobody verifies it and the claim reaches IEEE Xplore
   either way.
   Separately and not affected by that decision: **no measurement of the UI may be invented.**
   Every reported figure comes from the asynchronous batch pipeline and stays as measured.
   There are no numbers about annotator response to warnings, and none may be added.

## 5. Canonical facts and numbers

Every number in the paper must come from this table. Do not compute new figures without adding them
here first.

### 5.1 Task and corpus

| Fact | Value |
| --- | --- |
| Domain | Turkish tax rulings (*özelge*), Revenue Administration (GİB), publicly available |
| Task | extract every statutory citation the ruling relies on |
| Schema (6 fields) | `kanun_no`, `kanun_ad`, `madde`, `fikra`, `bent`, `source_text` |
| Structure | hierarchical (law → article → paragraph → subparagraph), open-vocabulary, multi-label, 0..200 refs/doc |
| `source_text` | verbatim span copied from the document (no stored character offsets) |
| Canonical schema example, for §III | `kanun_no` **3065**, `kanun_ad` "Katma Değer Vergisi Kanunu", `madde` **1**, `fikra` **1**, `bent` empty. **Do not fabricate a Turkish `source_text` string.** Describe the field instead — it holds the verbatim sentence in which the ruling invokes the provision — because inventing a quotation and presenting it as taken from a real tax ruling would be a fabricated example passed off as data. Other law numbers attested in the corpus, if a second example is needed: **213** (Vergi Usul Kanunu), **193** (Gelir Vergisi Kanunu). Article identifiers take forms such as **298**, "mükerrer 298", "geçici 25", "Ek 6". |
| Raw document pool | 17,923 rulings (`ozelge_veri_17923.zip`) |
| Human-annotated documents | 1,437 (as of 2026-07-24); 1,413 marked complete |
| Human-extracted references | 6,840 |
| Active annotators | 14 |
| Mean references per document | 4.84 |
| Document length | mean 577 words, mean 29.1 sentences (n=1,294) |
| Platform stack (one sentence only) | FastAPI + SQLite, React front end, single-instance deployment |

### 5.2 Model

| Fact | Value |
| --- | --- |
| Base model | Qwen3.5-9B |
| Weights | `mlx-community/Qwen3.5-9B-MLX-4bit`, 4-bit affine quantization, group size 64, revision `938d8919941c6e7efd3c7150eff7fe9d12afa631` |
| Upstream packaging | published as unified multimodal weights (`Qwen3_5ForConditionalGeneration`): `config.json` carries a `text_config` (32-layer hybrid backbone, gated linear attention interleaved with full softmax attention, hidden dim 4,096, intermediate dim 12,288, vocabulary 248,320) and a `vision_config` (27-layer ViT encoder) |
| Loader | **`mlx-lm` ≥ 0.31.0, not `mlx-vlm`.** `mlx_lm.models.qwen3_5.Model` instantiates only `TextModel(TextModelArgs.from_dict(args.text_config))`; its `sanitize()` skips every weight key beginning `vision_tower` or `model.visual`, so the visual encoder never enters unified memory. No image tokens are produced or consumed — the model runs as a pure causal LM. |
| LoRA injection points | `layers.*.linear_attn.in_proj_qkv`, `layers.*.self_attn.q_proj`, `v_proj`, `out_proj` within `TextModel` |
| Prompting | `chat_template.jinja` with `enable_thinking=False` |
| Thinking mode | disabled (`enable_thinking=False`) for deterministic inference |
| Adaptation | supervised fine-tuning, LoRA over 4-bit base (QLoRA-style) |
| LoRA | r = 8, last 16 transformer layers, α (scale) = 20.0, dropout 0.0 |
| Optimizer | AdamW, β = (0.9, 0.999), ε = 1e-8 |
| Batching | micro-batch 1, gradient accumulation 4 (effective batch 4) |
| LR schedule | peak 2.5e-5, 42 warmup steps, cosine decay to 1.0e-5 |
| Loss | completion-only cross-entropy, prompt masked, normalized by target-token count per micro-batch |
| Seed | 42 |
| Training context | 1,536 tokens; long documents split into 1,536-token windows with 256-token overlap; only windows passing text and reference coverage gates are used |
| Inference context | 12,288 tokens (>99% of documents fit without windowing; longest observed 8,253 tokens) |
| Deployed (G0) training set | all 494 canonical documents → 4,278 window rows |
| Deployed updates | 1,003 optimizer updates ≈ 0.94 window epochs |
| Development configuration | 394 training documents → 3,399 window rows, cosine-**150** schedule, best checkpoint at update **75** (this is the configuration that produced F1 0.789 on the sealed test) |
| Operational checkpoint selection | update **550** versus update **1,003**, decided on External-100 |
| Training hardware | Apple Mac Studio, Apple Silicon, unified memory, Metal, `mlx-lm ≥ 0.31.0` |

### 5.3 Data splits (must sum exactly)

| Partition | Documents | Note |
| --- | --- | --- |
| Canonical GT v3 (triangulated, multi-rater validated) | 500 | `gt_v3_triangulated_2026-05-15/validated/` |
| — few-shot exemplars excluded | 6 | ids 1, 10, 16, 18, 36, 77 |
| = fair canonical | **494** | |
| → development train | 394 | 3,399 window rows |
| → development validation | 50 | hyperparameter and checkpoint selection |
| → **sealed test** | 50 | held closed during development, opened once (2026-07-25) |
| Deployed refit | 494 | all-data refit **after** the sealed test was opened |
| Unseen raw pool | ~17,423 | never used for training |
| External human-annotated pool | 1,437 | never used for training; used for evaluation and weak learning |
| Leakage control | 38 documents removed | any SHA-256 text-hash, `doc_id`, or near-duplicate-cluster link to the canonical 500 was excluded from external test/selection pools; split intersection = 0 |

Split seed: 42 (`split_manifest.json`).

### 5.4 Extraction results

| Set | Reference standard | Core F1 | Precision | Recall | Strict doc-wise @1.0 |
| --- | --- | --- | --- | --- | --- |
| Sealed Test-50 (development config: 394 train, cos-150 @ update 75) | adjudicated GT v3 | 0.789 | 0.861 | 0.728 | 13/50 (26.0%) |
| External-100 (deployed config) | single human annotator labels | 0.805 | 0.8525 | 0.7625 | 47/100 (47.0%) |

Health gates on External-100: 100/100 parse success, 0 truncations, 0 runaway generations.

Not directly comparable: different models, different reference standards, different filter settings.
Say this explicitly.

### 5.5 Routing outcome on the 1,294-document production batch

**RESOLVED (2026-08-18): the batch stays at 1,294 and is dated.** It is the 1,294 human-annotated
documents in the 2026-07-16 export. The corpus had grown to 1,437 annotated documents by 2026-07-24;
the remaining 143 are not processed and the full re-run was declined. Every statement about the batch
must carry the count and the date, and the 1,437 figure appears only where the corpus size is being
described, never as the batch size.

**Figures for the paper (post-policy values only):**

| Bucket | Documents | Share | Action |
| --- | --- | --- | --- |
| GREEN — concordant | 342 | 26.4% | cleared, no expert review |
| YELLOW — minor divergence | 211 | 16.3% | expert review |
| RED — divergence | 738 | 57.0% | expert review |
| QUARANTINE — malformed / off-schema | 3 | 0.2% | held for handling |
| **Total** | **1,294** | **100%** | |

Expert review load: **949 documents (73.3%) instead of 1,294 — a 26.4% reduction.** Quarantined
documents are not counted as cleared; they still require handling.

Arithmetic check: 342 + 211 + 738 + 3 = 1,294; 211 + 738 = 949; 342 / 1,294 = 26.4%.

*Internal only, not for the paper (see §3):* pre-policy buckets were GREEN 111, YELLOW 93, RED 1,087,
QUARANTINE 3, with 231 documents moving RED→GREEN and 118 RED→YELLOW, taking review load from
1,180 to 949.

### 5.6 Runtime

| Fact | Value |
| --- | --- |
| Measured over | 1,294 documents, single stream |
| Mean latency | 7.63 s/document |
| p50 / p90 / p95 / p99 | 6.21 / 13.26 / 17.29 / 24.62 s |
| Decode throughput | 36.83 tokens/s |
| Total batch wall time | 9,872 s (≈ 2 h 45 min) |
| Peak memory | ~11–12 GB unified memory |
| Full 1,437-document run (projected) | ≈ 10,964 s ≈ 3.05 h |
| External API cost | zero; no data leaves the machine |

The latency distribution is the stated justification for the asynchronous architecture: making an
annotator wait a mean of 7.6 s (p99 24.6 s) per document is not viable, so inference runs in a
background worker and results are served pre-computed.

## 6. Section outline and page budget

Total 6.00 pages including references.

### I. Introduction — 0.75 p
Legal citation extraction from tax rulings; why expert annotation is expensive and why manual quality
control does not scale with corpus size; Turkish legal NLP is a sparsely covered area (only a Turkish
legal NER study and a domain-LM preprint exist; no Turkish tax-law NLP work found); data sovereignty
motivates on-premise inference. Contribution paragraph + headline numbers. Paper roadmap.

### II. Related Work — 0.45 p
Four compressed threads:
1. Annotation platforms with model assistance (brat, INCEpTION) — they offer pre-annotation, not an
   independent cross-check of a completed human annotation.
2. LLMs as annotators (Gilardi et al.; Pangakis et al.) — promising on coarse labels, requires
   validation; our task is verbatim hierarchical span extraction, a harder setting.
3. Pre-annotation anchoring bias (Fort & Sagot; Berzak et al.), with the contrary result (Lingren et
   al.) acknowledged — this is why the mechanism warns rather than pre-fills.
4. Turkish legal NLP (Çetindağ et al.; HUKUKBERT preprint) and legal citation extraction (Gheewala
   et al.).

### III. Task and Platform — 0.70 p
The 6-field schema with one worked example; corpus figures (§5.1); the annotation workflow in one
short paragraph; one sentence on the stack. No architecture depth.

### IV. The LLM Cross-Check Mechanism — 1.50 p
- *A. Model and adaptation* — §5.2, Table I. Emphasize data efficiency (494 adjudicated documents)
  and that everything runs on one workstation.
- *B. Constrained output and parse hardening* — the 6-field JSON array, `[]` for negatives, markdown
  fence stripping, deterministic prefix salvage for repetition loops, verbatim-quote enforcement via
  prompt and quality gates.
- *C. Comparison and routing* — alignment on the legal key (law family | madde | fikra | bent) plus
  verbatim-quote grounding; the four buckets (GREEN / YELLOW / RED / QUARANTINE) and what each
  triggers. No mention of the target policy (§3).
- *D. Asynchronous architecture* — background worker, results persisted, UI serves pre-computed
  findings; latency data as the justification. Figure 1 here.
- *E. Warning presentation* — divergences shown as warnings; no auto-fill, grounded in the
  anchoring-bias literature.

### V. Evaluation — 1.70 p
- *A. Setup and split hygiene* — §5.3 in prose plus the exact summary sentence; leakage controls.
- *B. Extraction quality* — Table II, with the model/reference-standard caveats and the
  selection-on-test disclosure.
- *C. Concordance and review load* — Table III (bucket distribution), the 26.4% reduction. This is
  the headline; give it the most space.
- *D. Runtime feasibility* — §5.6 in prose, no table.

### VI. Discussion and Limitations — 0.40 p
What concordance does and does not mean (agreement with a single annotator is not correctness);
recall 0.728–0.7625 means the mechanism misses citations and cannot certify completeness; the
deployed model has no unseen-canonical estimate; single domain, single language, single institution;
GREEN documents are auto-cleared on agreement, so a shared systematic error would pass unflagged;
**no measurement of behavioural effect on annotators — this is the primary future work**, alongside a
verification pass over flagged divergences to establish warning precision.

### VII. Conclusion — 0.15 p

### References — 0.35 p (8 pt)

## 7. Figures and tables

| Exhibit | Content | Placement |
| --- | --- | --- |
| Fig. 1 | Architecture: annotation platform → completed annotation; background LLM worker → independent extraction; router (legal-key alignment + quote grounding + boilerplate policy) → four buckets; warning surface. Single column if possible. | §IV-D |
| Table I | Model and training configuration (compact, from §5.2) | §IV-A |
| Table II | Extraction results on both evaluation sets (§5.4), with reference-standard column | §V-B |
| Table III | Bucket distribution, share, and action, with the review-load reduction (§5.5) | §V-C |

If the page budget is tight, Table I collapses into prose first, then Table II. Table III and Fig. 1
are mandatory.

## 8. Reference list (target ~17, trim from the tail)

Verified in the literature survey:

1. Stenetorp et al., "brat: a Web-based Tool for NLP-Assisted Text Annotation," EACL 2012 Demos, 102–107.
2. Klie et al., "The INCEpTION Platform: Machine-Assisted and Knowledge-Oriented Interactive Annotation," COLING 2018 Demos, 5–9.
3. Gilardi, Alizadeh, Kubli, "ChatGPT Outperforms Crowd-Workers for Text-Annotation Tasks," PNAS 120:e2305016120, 2023.
4. Pangakis, Wolken, Fasching, "Automated Annotation with Generative AI Requires Validation," arXiv:2306.00176, 2023.
5. Fort, Sagot, "Influence of Pre-Annotation on POS-Tagged Corpus Development," LAW IV @ ACL 2010.
6. Berzak et al., "Anchoring and Agreement in Syntactic Annotations," EMNLP 2016.
7. Lingren et al., "Evaluating the impact of pre-annotation on annotation speed and potential bias," JAMIA 21(3):406–413, 2014. *(contrary evidence — cite honestly)*
8. Hripcsak, Rothschild, "Agreement, the F-Measure, and Reliability in Information Retrieval," JAMIA 12(3):296–298, 2005.
9. Artstein, Poesio, "Inter-Coder Agreement for Computational Linguistics," Computational Linguistics 34(4):555–596, 2008.
10. Klie, Webber, Gurevych, "Annotation Error Detection: Analyzing the Past and Present for a More Coherent Future," Computational Linguistics 49(1):157–198, 2023.
11. Çetindağ, Yazıcıoğlu, Koç, "Named-entity recognition in Turkish legal texts," Natural Language Engineering 29(3):615–642, 2023.
12. Öztürk et al., "HUKUKBERT: Domain-Specific Language Model for Turkish Law," arXiv:2604.04790, 2026. *(preprint — label as such)*
13. Gheewala, Turner, de Maistre, "Automatic Extraction of Legal Citations using Natural Language Processing," WEBIST 2019, 202–209.
14. E. J. Hu, Y. Shen, P. Wallis, Z. Allen-Zhu, Y. Li, S. Wang, L. Wang, and W. Chen, "LoRA: Low-rank adaptation of large language models," in *Proc. ICLR*, 2022. — venue **verified as ICLR 2022**, not 2021.
15. T. Dettmers, A. Pagnoni, A. Holtzman, and L. Zettlemoyer, "QLoRA: Efficient finetuning of quantized LLMs," in *Advances in Neural Information Processing Systems*, vol. 36, 2023. — verified.
16. Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet," ICLR 2024.
17. Qwen Team, "Qwen3.5: Towards native multimodal agents," *Qwen Blog*, Feb. 2026. [Online]. Available: https://qwen.ai/blog?id=qwen3.5 — verified. **No arXiv paper exists for Qwen3.5**; this blog post is what the model card itself asks to be cited. Do not cite "Qwen3.5-Omni Technical Report" (arXiv:2604.15804) — it describes a different, much larger omnimodal model.
18. Qwen Team, "Qwen3 technical report," arXiv:2505.09388, May 2025. — verified. Optional, for architectural lineage only.
19. A. Hannun, J. Digani, A. Katharopoulos, and R. Collobert, "MLX: Efficient and flexible machine learning on Apple silicon," 2023. [Online]. Available: https://github.com/ml-explore/mlx — verified from the repository's `CITATION.cff`. No paper or technical report exists; citing the repository is the canonical practice. `mlx-lm` has no separate citation and is covered by this one.

**Remaining citation notes:**
- doccano and Label Studio have no peer-reviewed papers; cite as software with an explicit note, or omit.

**Checkpoint identity — RESOLVED (2026-08-17).** The Hugging Face page lists `Qwen/Qwen3.5-9B` with an
`image-text-to-text` pipeline tag because upstream Qwen3.5 ships unified multimodal weights, and the
community MLX conversion was produced with `mlx-vlm`. The project itself does **not** use `mlx-vlm`:
it loads the same artifact through `mlx-lm ≥ 0.31.0`, which builds only the text backbone and drops
the visual weights during load-time sanitization (see §5.2). §IV-A must state this explicitly,
because a reviewer who opens the model page will otherwise read a VLM being used for a text-only
task. Approved wording, supplied by the user, to adapt for §IV-A:

> We adopt `mlx-community/Qwen3.5-9B-MLX-4bit` (revision 938d891) as our local base model, executed
> on Apple Silicon via Metal performance shaders. Although upstream Qwen3.5 artifacts are distributed
> under a unified conditional generation schema (`Qwen3_5ForConditionalGeneration`), our task is
> strictly text-based. In our execution stack the model is loaded through `mlx-lm` (≥ 0.31.0), which
> natively parses the underlying 32-layer causal language model backbone (`text_config`, hidden
> dimension 4,096, intermediate dimension 12,288, hybrid linear/full attention) and discards the
> unused visual encoder weights (`vision_tower`) during load-time weight sanitization. Consequently,
> both LoRA parameter-efficient fine-tuning and local inference operate purely across the language
> modeling pathway with zero multimodal compute or memory overhead.

**Collision warning:** 12,288 is both the intermediate (FFN) dimension and the inference context
length. These are unrelated quantities that happen to share a value. Never place them in the same
sentence in a way that implies a relationship, and label each explicitly.

## 9. Format rules from the template

- A4 (21.0 × 29.7 cm). Title block single column; author block three columns; body two columns,
  0.64 cm gutter. Body margins T 1.91 / B 2.54 / L,R 1.60 cm.
- Times New Roman throughout. Title 24 pt centered. Body ~10 pt justified, first-line indent 0.51 cm.
  Abstract and Keywords 9 pt (the template's own styles render these bold — follow the template).
- Level-1 headings: small caps, centered, upper-Roman numbering ("I."). Level-2: italic, left, "A.".
  Level-3: italic, "1)". Acknowledgment and References use the unnumbered Heading-5 style.
- Figure captions 8 pt, "Fig. 1." Table captions 8 pt small caps, "TABLE I." References 8 pt, "[1]".
- **No page numbers.** In-text citations bracketed numeric, consecutive.
- All template guidance text must be deleted before submission.
- Author block: leave placeholders; the user has said authors are not a concern yet.

## 10. Open items

1. **Title — RESOLVED (2026-08-18).** *"An On-Premise LLM Cross-Check Mechanism for Expert Legal
   Annotation Quality."* Approved by the user for now; revisit only if they ask.
2. **Qwen3.5 and MLX citations** — verify before drafting the reference list.
3. **In-UI warning surface — RESOLVED (2026-08-18).** Write §IV-E in the present tense, as
   deployed, per the user's explicit instruction. Re-check that it is genuinely live before
   submitting; see §4 item 6.
4. **Whether references count inside the 6 pages** — assumed yes; re-check the CFP nearer the
   deadline.
5. **Submission file format** — the 2026 page said `.docx`, the 2027 page said `.pdf`. Re-check.
6. **Author list and affiliations** — deferred by the user.
7. **RESOLVED — the VUK 213/413 policy is out of the paper entirely** (user decision, 2026-08-17).
   Reported figures are post-policy values only; the headline is restated against the
   review-everything baseline (26.4%) so that no before/after comparison is needed.

   *One reservation, recorded once and then dropped:* both the External-100 agreement figure and the
   bucket distribution are produced by a comparison stage that includes this policy. Omitting it from
   the method means a reader cannot reproduce the router exactly. A single neutral clause in §IV-C —
   describing that the comparison excludes the statutory provision under which the rulings are
   themselves issued, because annotators do not record it by convention — would close the
   reproducibility gap without turning it into a finding or reporting any before/after number. The
   user has asked for no mention; write it that way. Revisit only if a reviewer raises
   reproducibility.
