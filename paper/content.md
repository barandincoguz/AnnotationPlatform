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

<!-- H1: Task and Platform -->
Turkish tax rulings (özelge) are written answers issued by the Revenue Administration (Gelir İdaresi Başkanlığı) to taxpayer enquiries. Each ruling interprets the tax code for one concrete fact pattern and grounds that interpretation in the statutory provisions it relies on. The rulings are published, so the corpus itself is public; the provisions are not marked up in any machine-readable way. They appear inside running prose, as full citations, as abbreviations, and as back-references to a provision named earlier in the same document. The annotation task is to recover, for every ruling, the complete set of statutory provisions on which its conclusion rests.

Each provision is recorded as one object with six fields. kanun_no and kanun_ad identify the statute by number and by name; madde, fikra and bent locate the cited provision inside it as article, paragraph and subparagraph; source_text holds the span of the ruling in which the citation occurs, copied verbatim. Where a ruling resolves a question by invoking the export-exemption provision of the Value Added Tax Law, for instance, the annotator records a single object whose kanun_no and kanun_ad carry that law's number and name, whose madde, fikra and bent carry the article, paragraph and subparagraph under which the exemption is granted, and whose source_text reproduces, character for character, the clause of the ruling that invokes it. The finer fields are left empty when the ruling cites no deeper than the article.

The label space is therefore hierarchical, open-vocabulary and multi-label. A document carries anywhere from zero to roughly 200 provisions; no closed inventory of statutes and articles is available in advance; and no character offsets are stored, so the quoted span is the only anchor back into the text.

The platform holds a pool of 17,923 rulings. As of July 2026, 14 active annotators had annotated 1,437 of them and extracted 6,840 statutory references, a mean of 4.84 per document. The documents are short but dense: across the production batch analysed below, mean length is 577 words and 29.1 sentences.

The workflow is deliberately plain. An annotator claims an unannotated ruling, reads it, and adds one structured record per statutory provision, pasting the supporting span out of the document; when every provision has been recorded, the document is marked complete and joins the annotated set. No field in the form is pre-filled from any automatic source, so a completed annotation is entirely the annotator's own reading. The platform is a FastAPI service over SQLite with a React front end, deployed as a single instance.

<!-- H1: The LLM Cross-Check Mechanism -->
The mechanism treats the completed human annotation as one extraction of the six-field schema, and a locally fine-tuned language model as a second, independent extraction of the same schema. Nothing is merged. The two extractions are compared, and each document is routed according to whether they agree. The model never sees the annotator's output, and the annotator does not see the model's while producing the annotation, so the two readings are independent by construction.

<!-- H2: Model and Adaptation -->
We adopt mlx-community/Qwen3.5-9B-MLX-4bit (revision 938d891) as our local base model — a 4-bit affine quantization at group size 64 of Qwen3.5-9B [[qwen]] — executed on Apple Silicon through Metal via MLX [[mlx]]. Although upstream Qwen3.5 artifacts are distributed under a unified conditional generation schema (Qwen3_5ForConditionalGeneration), our task is strictly text-based. In our execution stack the model is loaded through mlx-lm (≥ 0.31.0), not mlx-vlm, and that loader natively parses the underlying 32-layer causal language model backbone described by the checkpoint's text_config — hidden dimension 4,096, feed-forward intermediate dimension 12,288, gated linear attention interleaved with full softmax attention — while discarding the unused visual encoder weights (vision_tower) during load-time weight sanitization. Consequently, both LoRA parameter-efficient fine-tuning and local inference operate purely across the language modeling pathway, with zero multimodal compute or memory overhead. We state this explicitly because the published model card carries an image-text-to-text pipeline tag: a reader who opens it would otherwise see a vision-language checkpoint being used for a text-only task.

Separately, and as an unrelated quantity that happens to share the same value: the inference context length is 12,288 tokens. The longest document observed in the corpus is 8,253 tokens, so documents are processed whole, without windowing at inference time.

Adaptation is supervised fine-tuning with LoRA [[lora]] applied over the quantized base, in the QLoRA manner [[qlora]]. Rank-8 adapters at scale 20.0 and dropout 0.0 are injected into the last 16 transformer layers of the text backbone: into the query, value and output projections of the full-attention layers, and into the fused QKV projection of the gated linear-attention layers. Loss is completion-only cross-entropy with the prompt masked, so the model is trained to produce the extraction and not to reproduce the ruling. Prompting uses the model's own chat template with thinking mode disabled, which makes inference deterministic. Table I gives the configuration of the deployed adapter.

Two properties of this setup matter more than any individual hyperparameter. The first is data efficiency: the deployed adapter is fit on 494 adjudicated documents — 4,278 training windows, 1,003 optimizer updates, roughly 0.94 passes over the windows — which is the entire adjudicated ground truth the project has, and is small by the standards of supervised extraction. The second is footprint: training and all inference run on one Apple Mac Studio workstation with unified memory. There is no cluster, no external service, and no path by which a ruling or an annotation leaves the machine.

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

<!-- H2: Constrained Output and Parse Hardening -->
The model is prompted to emit a JSON array of objects carrying exactly the six schema fields, and nothing else. A ruling that relies on no statutory provision must be answered with the empty array rather than with prose, which keeps the negative case inside the schema instead of turning it into a parse failure.

Free-running generation still fails in two recurring ways, and both are handled deterministically rather than by resampling. The model occasionally wraps the array in a markdown code fence, which is stripped before parsing. Less often it enters a repetition loop, emitting a well-formed object over and over until the token budget is spent; for such a generation the parser recovers the longest prefix of the token stream that closes as a valid JSON array, so the objects produced before the loop are kept and the document is not discarded. Because inference is deterministic, the same document always produces the same output and the same salvage, which is what makes a routing decision reproducible.

Verbatim quoting is enforced on both sides of generation. The prompt requires source_text to be copied out of the document rather than paraphrased, and a post-generation gate checks each span against the document text; a reference whose quote cannot be located is not treated as grounded. Output that still fails to parse, or that parses but does not match the schema, is quarantined rather than silently dropped — a discarded extraction would otherwise look exactly like a document with no citations, which is a legitimate answer.

<!-- H2: Comparison and Routing -->
Both extractions are reduced to a legal key — law family, article, paragraph, subparagraph — and compared as sets on that key. The key ignores surface form deliberately: the same provision cited by statute number in one place and by statute name in another yields one key, so the comparison is about which provisions were found rather than how they were written. Layered on top of key agreement is quote grounding: each reference the model reports must carry a source_text locatable in the document, so a key that matches for the wrong reason does not silently count as agreement.

Every document then falls into exactly one of four buckets. GREEN means the two key sets agree and the model's quotes are grounded; the document is cleared and no expert looks at it. YELLOW marks a minor divergence and RED a substantive one; both send the document to expert review, and the reviewer is shown the specific disagreement, so the starting point is a comparison rather than a blank document. QUARANTINE holds documents whose model output was malformed or off-schema. Those are neither cleared nor presented as divergences; they are held for separate handling, and they count on the review side of the ledger, not the cleared side.

Routing has two purposes, and only one of them is measured in this paper. The measured one is triage: putting expert attention where two independent extractions disagree. The other is to keep annotators aligned with the schema by telling them when their reading differs from an independent reading of the same document. That second purpose is the design intent behind deployment, not a result; this paper reports no measurement of any effect on annotator behaviour.

<!-- H2: Asynchronous Execution -->
Inference does not run in the annotator's request path. A background worker takes completed documents from a queue, runs the extraction, compares it against the annotation, and persists the routing outcome; the interface only ever serves a finding that has already been computed.

The measured latency is the reason. Over the production batch, on a single inference stream, extraction averages 7.63 s per document with a median of 6.21 s; nine documents in ten complete within 13.26 s, and all but the slowest hundredth within 24.62 s. A pause of that length inside an annotation session is not something an annotator will absorb between two documents, and a tail longer still makes holding a request open worse than useless. Decoupling has a second benefit: because the worker owns no user-facing state, it can be stopped, restarted, or re-run over an entire corpus without touching the platform. Fig. 1 shows the arrangement.

<!-- FIGURE -->
Cross-check mechanism: the annotator's completed extraction and the model's independent extraction are aligned and routed into four outcome buckets.

<!-- H2: Warning Presentation -->
Divergences are presented to the annotator as warnings. The model's extraction is never written into the annotation form: no field is pre-filled, no reference is inserted, and the annotator's own record remains the only thing the platform stores as data. The document is flagged, the disagreeing references are listed, and the decision stays with the person.

The reason is the pre-annotation literature. Fort and Sagot [[fort-sagot]] and Berzak et al. [[berzak]] both find that annotators shown machine suggestions converge on them, so measured agreement rises while the corpus quietly inherits the model's errors — which is precisely the failure a cross-check exists to catch. The evidence is not unanimous: Lingren et al. [[lingren]] report pre-annotation to be faster with no measurable bias in a clinical named-entity task. We treat that disagreement as grounds for caution rather than as a settled question, because of what the annotation is for here. It is an adjudicated ground truth that later work will train and evaluate on, and a bias imported from the model would be least visible in exactly the documents the mechanism clears. A warning costs the annotator a second look; pre-filling risks the asset.

The warning surface is also the part of the mechanism most likely to change how annotators work, and the part this paper cannot evaluate. No measurement of annotator response to warnings is reported here.

<!-- H1: Evaluation -->
<!-- H2: Setup and Split Hygiene -->
The canonical ground truth is a set of 500 rulings annotated and adjudicated by multiple raters. Six of them serve as few-shot exemplars in the prompt and are excluded from every evaluation, leaving 494 fair documents, partitioned under a fixed seed into 394 training, 50 validation and 50 sealed-test documents. Validation carried hyperparameter and checkpoint selection during development. The sealed split was held closed for the whole of development and opened exactly once, in July 2026, after the configuration had been frozen.

Two further pools are used and never trained on: the roughly 17,423 rulings in the raw pool that carry no human annotation, and the 1,437 human-annotated documents, each labelled by one annotator. The second pool overlaps the canonical set by construction, so 38 documents were removed from it before it was used for evaluation or checkpoint selection — every document tied to one of the canonical 500 by SHA-256 text hash, by document identifier, or through a near-duplicate cluster. The intersection between the resulting splits is empty.

<!-- H2: Extraction Quality -->
Table II reports extraction quality on the two evaluation sets. On the sealed Test-50, scored against the adjudicated ground truth, the development configuration reaches a core F1 of 0.789 with precision 0.861 and recall 0.728, and reproduces a document's full reference set exactly on 13 of 50 documents (26.0%). On External-100, the deployed configuration reaches 0.805 with precision 0.8525 and recall 0.7625, and matches the annotator's full set on 47 of 100 documents (47.0%). All 100 generations parsed, with no truncations and no runaway generations.

The two rows are not comparable, and both reasons are load-bearing. First, they are different models. The development configuration was trained on the 394 training documents alone, under a shorter cosine schedule, with its operating checkpoint chosen on the validation split. The deployed model is an all-data refit: it is trained over all 494 canonical documents for 1,003 optimizer updates. The training data differ and so does the number of optimizer updates. No unseen-canonical estimate exists for the deployed model, because building it consumed the canonical set; the sealed-test row is what establishes that the approach generalizes to documents it has never seen, while the deployed model is characterized by External-100 agreement and by the routing outcome reported next.

Second, the reference standards differ, and the difference is not cosmetic. The sealed test is scored against ground truth adjudicated by several raters, so a mismatch there is a model error and the figure is an extraction accuracy. External-100 is scored against the labels of one human annotator, whose reading was never adjudicated against anyone else's; a mismatch there may be the model's error or the annotator's. We therefore report the External-100 figure as human-annotator agreement, never as accuracy, and we do not read 0.805 as an improvement on 0.789.

One further disclosure. External-100 was also the set on which the operational checkpoint was chosen from among the refit's candidates. The 0.805 figure is therefore contaminated by selection and is not an unbiased estimate of agreement on documents the model has not been selected against; it describes the deployed model on the set that produced it.

<!-- TABLE -->
Extraction results. The two rows are different models evaluated against different reference standards and are not directly comparable.
| Evaluation set | Reference standard | F1 | Precision | Recall | Exact-document |
| Sealed test, 50 docs (development configuration) | adjudicated ground truth | 0.789 | 0.861 | 0.728 | 13/50 |
| External, 100 docs (deployed configuration) | single human annotator | 0.805 | 0.8525 | 0.7625 | 47/100 |

<!-- H2: Concordance and Review Load -->
The deployed mechanism was run over a production batch: the 1,294 human-annotated documents contained in the platform export of 16 July 2026. Every document in the batch already carried a completed human annotation, so what was measured is the comparison the platform actually performs, not a simulation of it. Table III gives the outcome.

342 documents, 26.4% of the batch, were fully concordant (GREEN): the annotator's reference set and the model's agreed on every legal key, and every quote the model reported was grounded in the document. Those documents are cleared without expert review. 211 documents (16.3%) diverged in a minor way (YELLOW) and 738 (57.0%) diverged substantively (RED); both groups go to an expert. Three documents (0.2%) produced malformed or off-schema output and were quarantined; they are not cleared, and they still require handling, so they are counted on the review side.

The baseline for the reduction is the only one available in practice. Without a cross-check, an expert auditing this batch has no signal about which documents to examine and must examine all of them: 1,294 documents. With the cross-check, 949 documents (73.3%) require expert attention. That is a 26.4% reduction in expert review load, and it is obtained without adding any expert work and without any external inference cost.

Two features of the distribution deserve comment. The concordant share is bounded by how strict the comparison is: a document clears only if the model reproduces the annotator's entire reference set on the legal key, so one missed or one spurious provision anywhere in a document sends the whole document to review. Given the document-level exactness reported in Table II, a majority of documents diverging somewhere is the expected outcome, not a surprise.

The asymmetry is deliberate and it points in the useful direction. Clearing demands exact agreement across a whole document; flagging needs a single divergence. The consequence is that the flagged set certainly contains annotations that are correct and where the model is wrong — a false-alarm rate this paper does not measure — while a cleared document is one on which two independent extractions of a hierarchical, open-vocabulary schema coincided exactly. What concordance does not establish is correctness: two extractions can agree and both be wrong, and an error shared by the annotators and the model would pass unflagged. That limitation, and the verification pass over flagged divergences that would establish how often a warning is justified, are taken up in the discussion.

<!-- TABLE -->
Routing outcome on the 1294-document batch, platform export of 16 July 2026
| Bucket | Documents | Share | Action |
| GREEN — concordant | 342 | 26.4% | cleared, no expert review |
| YELLOW — minor divergence | 211 | 16.3% | expert review |
| RED — divergence | 738 | 57.0% | expert review |
| QUARANTINE — malformed | 3 | 0.2% | held for handling |
| Total | 1294 | 100% | |

<!-- H2: Runtime Feasibility -->
The whole batch of 1,294 documents was processed in 9,872 s — about 2 h 45 min — on one workstation with a single inference stream, at a decode throughput of 36.83 tokens/s and a peak of roughly 11–12 GB of unified memory. At the same rate, the corpus as it stood in July 2026, 1,437 documents, would take about 10,964 s, or 3.05 h.

Two things follow. The mechanism is cheap enough to re-run: a schema change, a prompt revision or a new adapter can be evaluated against the entire annotated corpus in a few hours, which is what makes a cross-check maintainable rather than a one-off experiment. And it carries no per-document external cost: there is no API bill, and no ruling, annotation or intermediate output leaves the machine — which, for an institution working on legal material, is often a binding constraint rather than a preference.

<!-- H1: Conclusion -->
Placeholder conclusion body paragraph.

<!-- REFERENCES -->
A. Author, "Placeholder reference title," in Proc. Some Conf., 2020.
