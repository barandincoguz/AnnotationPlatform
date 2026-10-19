"""Build a new, auditable ARGE law/article dataset without changing its source.

No model calls, database access, training, or journal writes. The existing DQ
normalizer is reused with its source hashes locked into the output manifest.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
import tarfile
import unicodedata
import zipfile

sys.dont_write_bytecode = True
FIELDS = ("kanun_no", "kanun_ad", "madde")
NULLS = {"", "none", "null", "nan", "yok", "-", "—", "–", "n/a"}
SOURCE_ROOT = Path("/Users/student2/ner-project")
SOURCE_ART = SOURCE_ROOT / "artifacts/2026-09-16_arge-hizli-veri-temizleme"
DQ_ROOT = Path("/Users/student2/data-quality-checker")


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256")
    return digest.hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return value.translate(str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")).casefold()


def tokens(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", fold(value)))


def clean(value) -> str:
    value = " ".join(str(value or "").split()).strip()
    return "" if fold(value) in NULLS else value


def name_key(value: str) -> str:
    # Turkish possessive/case suffixes do not create a different law.
    return re.sub(r"\bkanun[a-z]*\b", "kanun", tokens(value)).strip()


def load_dq(root: Path):
    sys.path.insert(0, str(root / "src"))
    normalizer = importlib.import_module("data_quality_checker.normalization")
    text = importlib.import_module("data_quality_checker.text")
    expected = (root / "src/data_quality_checker/normalization.py").resolve()
    if Path(normalizer.__file__).resolve() != expected:
        raise ValueError("A different DQ installation was imported")
    return normalizer, text


class Processor:
    def __init__(self, normalizer, law_names: dict, provisions: dict):
        self.normalizer = normalizer
        self.law_names = law_names
        self.provisions = provisions
        self.aliases = defaultdict(set)
        for number, name in law_names.items():
            self.aliases[number].add(name)
            if name.startswith("Türk "):
                self.aliases[number].add(name.removeprefix("Türk "))
        for alias, name in normalizer.LAW_NAME_ALIASES.items():
            for number, canonical in law_names.items():
                if name_key(name) == name_key(canonical):
                    self.aliases[number].add(alias)

    def article(self, number: str, raw) -> str:
        value = clean(raw)
        # "mülga" describes repeal status, not a different article.
        value = re.sub(r"^m[uü]lga\s+", "", value, flags=re.IGNORECASE)
        # Use the legislation-backed registry BEFORE the case-based normalizer.
        suffix = re.fullmatch(r"((?:(?:mükerrer|mukerrer|geçici|gecici|ek)\s+)?\d+)\s*/\s*([A-Za-zÇĞİÖŞÜçğıöşü])", value, re.IGNORECASE)
        if suffix:
            base = self.normalizer.normalize_article(suffix[1])
            letter = suffix[2].upper()
            key = f"{number}/{base}"
            if f"{key}/{letter}" in self.provisions["eklenen_madde"]:
                return f"{base}/{letter}"
            for section, field in (("madde_ici_bolum", "bolumler"), ("fikra_ici_bent", "bentler")):
                entry = self.provisions[section].get(key, {})
                if letter in {s.upper() for s in entry.get(field, [])}:
                    return base
        value = re.sub(r"\bila\s+(?:ek|geçici|gecici|mükerrer|mukerrer)\s+(?=\d)", "ila ", value, flags=re.IGNORECASE)
        return self.normalizer.normalize_article(value)

    def project(self, raw: dict) -> dict:
        normalized = self.normalizer.normalize_reference(
            {k: clean(raw.get(k)) for k in (*FIELDS, "source_text")},
            resolve_number_from_name=False,
        )
        number = normalized["kanun_no"]
        name = clean(normalized["kanun_ad"])
        if number in self.law_names:
            name = self.law_names[number]
        return {"kanun_no": number, "kanun_ad": name, "madde": self.article(number, raw.get("madde"))}

    def grounding(self, ref: dict, document: str, raw_name: str = "") -> dict:
        text = tokens(document)
        number = ref["kanun_no"]
        # A bare number could be a year, amount, paragraph or article of a
        # different law. Require law-number wording, or a law-name mention.
        number_match = None
        if number:
            number_match = re.search(
                rf"(?<!\d){re.escape(number)}\s+(?:sayili|numarali|nolu|no lu)\b"
                rf"|\bkanun(?:u|un|unun)?\s+(?:no|numarasi)\s+{re.escape(number)}(?!\d)",
                text,
            )
            if not number_match:
                # "7153 ve 7181 sayılı Kanunlar": both numbers name laws.
                for match in re.finditer(r"\b(\d+(?:\s+(?:ve\s+)?\d+)*)\s+(?:sayili|numarali)\b", text):
                    if number in re.findall(r"\d+", match[1]):
                        number_match = match
                        break
            if not number_match:
                # A legislative amendment's compact date-law/article notation
                # is not a random date or decree number.
                number_match = re.search(
                    rf"\bdegisik\s*:\s*\d{{1,2}}/\d{{1,2}}/\d{{4}}\s*-\s*{re.escape(number)}/\d+\s*md\b",
                    fold(document),
                )
        variants = {clean(ref["kanun_ad"]), *self.aliases.get(number, set())}
        # An arbitrary old name must not ground a DIFFERENT numbered law.
        # Use audited names/aliases for registered numbers; unregistered or
        # numberless references retain their actual written name.
        if number not in self.law_names:
            variants.add(clean(raw_name))
        doc_name_text = re.sub(r"\bkanun[a-z]*\b", "kanun", text)
        named = None
        for variant in sorted(variants, key=lambda v: (-len(v), v)):
            key = name_key(variant)
            if not key or key in {"kanun", "sayili kanun", "kanun hukmunde kararname"}:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", doc_name_text):
                named = variant
                break
            # Dotted abbreviations: V.U.K. is VUK, not three different words.
            if re.fullmatch(r"[a-z]{3,5}", key):
                dotted = r"\s+".join(key)
                if re.search(rf"\b{dotted}\b", text):
                    named = variant
                    break
        return {"number_mentioned": bool(number_match), "name_mentioned": bool(named),
                "name_variant": named, "grounded": bool(number_match or named)}

    def article_surface(self, ref: dict, document: str) -> bool:
        article = ref["madde"]
        if not article:
            return True
        plain = fold(document)
        parts = re.findall(r"\d+", article)
        # This is a conservative absence check, not a law/article binding
        # claim. Anaphora and collective lists remain valid.
        ordinals = {"1": "birinci", "2": "ikinci", "3": "ucuncu", "4": "dorduncu",
                    "5": "besinci", "6": "altinci", "7": "yedinci", "8": "sekizinci",
                    "9": "dokuzuncu", "10": "onuncu"}
        for part in parts:
            if re.search(rf"(?<!\d){re.escape(part)}(?!\d)", plain):
                continue
            word = ordinals.get(part)
            if word and re.search(rf"\b{word}\s+madde", plain):
                continue
            if any(int(m[1]) <= int(part) <= int(m[2]) and "madde" in plain[m.end():m.end()+65]
                   for m in re.finditer(r"(?<!\d)(\d+)\s*(?:-|–|ila|ilâ)\s*(\d+)(?!\d)", plain)):
                continue
            return False
        return True

    def identity(self, ref: dict, numbers_by_name: dict | None = None) -> tuple[str, str]:
        number = ref["kanun_no"]
        if not number and numbers_by_name:
            candidates = numbers_by_name.get(name_key(ref["kanun_ad"]), set())
            if len(candidates) == 1:
                number = next(iter(candidates))
        return (f"no:{number}" if number else f"name:{name_key(ref['kanun_ad'])}", ref["madde"])

    def process(self, doc_id: str, raw_refs: list[dict], text: str) -> tuple[list, list, list]:
        accepted, audit, issues = [], [], []
        name_fallbacks = defaultdict(set)
        for raw in raw_refs:
            ref = self.project(raw)
            if self.grounding(ref, text)["grounded"]:
                continue
            candidate = clean(raw.get("kanun_ad"))
            if not candidate:
                # Preserve a numberless NAME actually named in the original
                # annotation's evidence, rather than inventing its number.
                match = re.match(r"^([A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü]+)*)\s+Kanun\w*", clean(raw.get("source_text")))
                if match:
                    candidate = f"{match[1]} Kanunu"
            # A generic amendment tail is not a distinctive law name.
            if not candidate or name_key(candidate).startswith(("kanun ", "sayili ")):
                continue
            fallback = self.project({"kanun_no": "", "kanun_ad": candidate, "madde": raw.get("madde")})
            if self.grounding(fallback, text)["grounded"]:
                name_fallbacks[ref["kanun_no"]].add(fallback["kanun_ad"])
        for index, raw in enumerate(raw_refs):
            ref = self.project(raw)
            evidence = self.grounding(ref, text, clean(raw.get("kanun_ad")))
            fallback = False
            names = name_fallbacks.get(ref["kanun_no"], set())
            if not evidence["grounded"] and len(names) == 1:
                ref = self.project({"kanun_no": "", "kanun_ad": next(iter(names)), "madde": raw.get("madde")})
                evidence = self.grounding(ref, text)
                fallback = True
            reason = None
            if ref["kanun_no"] and not re.fullmatch(r"[1-9]\d*", ref["kanun_no"]):
                reason = "invalid_law_number"
            elif not ref["kanun_no"] and not ref["kanun_ad"]:
                reason = "missing_law_identity"
            elif not evidence["grounded"]:
                reason = "law_identity_absent_from_text"
            elif ref["madde"] and not re.fullmatch(r"(?:(?:geçici|mükerrer|ek) )?\d+(?:/[A-ZÇĞİÖŞÜ]| ila \d+)?", ref["madde"]):
                reason = "unreadable_article"
            elif not self.article_surface(ref, text):
                reason = "article_number_absent_from_text"
            elif ref["kanun_no"] == "213" and ref["madde"] == "413":
                reason = "excluded_footer_213_413"
            record = {"document_id": doc_id, "source_index": index, "original": raw,
                      "projected": ref, "evidence": evidence, "numberless_name_fallback": fallback}
            if reason:
                record.update(action="excluded_policy" if reason.startswith("excluded_") else "quarantine", reason=reason)
                if record["action"] == "quarantine":
                    issues.append(record)
            else:
                record["action"] = "accepted"
                accepted.append((ref, record))
            audit.append(record)
        numbers_by_name = defaultdict(set)
        for ref, _ in accepted:
            if ref["kanun_no"] and ref["kanun_ad"]:
                numbers_by_name[name_key(ref["kanun_ad"])].add(ref["kanun_no"])
        groups = defaultdict(list)
        for ref, record in accepted:
            groups[self.identity(ref, numbers_by_name)].append((ref, record))
        laws_with_articles = {law for law, article in groups if article}
        result = []
        for key, group in sorted(groups.items()):
            if not key[1] and key[0] in laws_with_articles:
                for _, record in group:
                    record.update(action="subsumed_law_only", identity=list(key))
                continue
            # Numbered spelling wins over a name-only equivalent; independent
            # of input order. Never deduplicate across different documents.
            group.sort(key=lambda pair: (not bool(pair[0]["kanun_no"]), json_bytes(pair[0]), pair[1]["source_index"]))
            representative = group[0][0]
            result.append(representative)
            group[0][1].update(action="kept", identity=list(key))
            for _, record in group[1:]:
                record.update(action="deduplicated", identity=list(key))
        return result, audit, issues


def exact_document_groups(documents: list[dict]) -> list[list[str]]:
    groups = defaultdict(list)
    for doc in documents:
        groups[hashlib.sha256(tokens(doc["text"]).encode()).hexdigest()].append(doc["doc_id"])
    return [sorted(ids) for _, ids in sorted(groups.items()) if len(ids) > 1]


def read_archive(path: Path) -> dict:
    docs = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            if not member.isfile() or not re.fullmatch(r"validated/doc_[a-z0-9]+\.json", member.name):
                continue
            doc = json.load(archive.extractfile(member))
            oid = doc["doc_id"]
            if oid in docs:
                raise ValueError(f"Duplicate input doc_id: {oid}")
            docs[oid] = doc
    if not docs:
        raise ValueError("No source documents")
    return docs


def build(args) -> dict:
    normalizer, text_tools = load_dq(args.dq_root)
    source = args.source_root
    art = source / "artifacts/2026-09-16_arge-hizli-veri-temizleme"
    inputs = {
        "source_archive": art / "dataset/validated_1525_docs.tar.gz",
        "source_rows": art / "dataset/cleaned_references.jsonl",
        "source_quarantine": art / "dataset/review/quarantine_remaining.jsonl",
        "law_names": art / "dataset/review/_canonical_law_names.json",
        "provision_registry": source / "artifacts/2026-09-18_ground-truth-hardening/data/law_provision_registry.json",
        "corpus": source / "ozelge_veri_17923.zip",
        "training_pool": source / "artifacts/2026-09-25_dq-loop-gt750/POOL.json",
        "selection": source / "artifacts/2026-09-19_gt750-promotion/SELECTION.json",
        "heldout_split": source / "data/ground_truth/gt_v8_gt750_law_article_2026-10-02/SPLIT.json",
        "generator": Path(__file__).resolve(),
        "pending_decisions": Path(__file__).with_name("arge_pending_decisions_2026-10-06.json"),
    }
    for name in ("normalization", "text", "contracts", "constants", "errors"):
        inputs[f"dq_{name}"] = args.dq_root / f"src/data_quality_checker/{name}.py"
    inputs["twins"] = source / "scripts/gt750/twins.py"
    locked = {key: {"path": str(path), "sha256": sha(path)} for key, path in inputs.items()}
    docs = read_archive(inputs["source_archive"])
    source_rows = [json.loads(line) for line in inputs["source_rows"].read_text().splitlines()]
    archived_rows = [dict(row, document_id=oid) for oid, doc in docs.items() for row in doc["references"]]
    if Counter(json_bytes(r) for r in source_rows) != Counter(json_bytes(r) for r in archived_rows):
        raise ValueError("Source archive and source JSONL disagree")
    with zipfile.ZipFile(inputs["corpus"]) as archive:
        corpus_rows = json.loads(archive.read("ozelge_veri.json"))
    corpus = {}
    for row in corpus_rows:
        if row.get("evrakOid") in docs:
            oid = row["evrakOid"]
            if oid in corpus:
                raise ValueError(f"Ambiguous corpus ID: {oid}")
            corpus[oid] = text_tools.html_to_text(row.get("htmlText"))
    if set(docs) != set(corpus) or any(not text for text in corpus.values()):
        raise ValueError("Missing/empty canonical HTML body for a source document")
    names = json.loads(inputs["law_names"].read_text())
    provisions = json.loads(inputs["provision_registry"].read_text())
    processor = Processor(normalizer, names, provisions)
    pool = json.loads(inputs["training_pool"].read_text())
    selection = json.loads(inputs["selection"].read_text())
    if pool["sources"]["selection_sha256"] != sha(inputs["selection"]):
        raise ValueError("Training pool selection fingerprint is stale")
    if pool["sources"]["split_sha256"] != sha(inputs["heldout_split"]):
        raise ValueError("Training pool does not match the current held-out split")
    if not set(pool["doc_ids"]) <= set(selection["remaining"]) <= set(docs):
        raise ValueError("Training pool is not a subset of the ARGE source")
    original_pending = [json.loads(line) for line in inputs["source_quarantine"].read_text().splitlines()]
    pending_decisions = json.loads(inputs["pending_decisions"].read_text())["decisions"]
    decisions = {(d["document_id"], json_bytes(d["reference"])): d for d in pending_decisions}
    pending_resolution = []
    blocked = set()
    for row in original_pending:
        ref = processor.project(row["reference"])
        decision = decisions.get((row["document_id"], json_bytes(ref)))
        if decision is None or decision["decision"] != "exclude_reference":
            blocked.add(row["document_id"])
        pending_resolution.append({"document_id": row["document_id"], "reference": ref,
                                   "decision": decision or {"decision": "unresolved"}})
    if len(decisions) != len(pending_decisions) or len(pending_resolution) != len(decisions):
        raise ValueError("Pending decisions do not correspond exactly to the original queue")
    output, row_audit, issues = [], [], []
    for oid, doc in sorted(docs.items()):
        refs, audit, findings = processor.process(oid, doc["references"], corpus[oid])
        output.append({"doc_id": oid, "text": corpus[oid], "references": refs})
        row_audit.extend(audit)
        issues.extend(findings)
        if findings:
            blocked.add(oid)
    exact = exact_document_groups(output)
    by_id = {doc["doc_id"]: doc for doc in output}
    duplicate_omitted = set()
    conflicts = []
    for group in exact:
        signatures = {json_bytes(by_id[oid]["references"]) for oid in group}
        if len(signatures) > 1:
            blocked.update(group)
            conflicts.append(group)
        else:
            eligible = sorted(oid for oid in group if oid in pool["doc_ids"] and oid not in blocked)
            duplicate_omitted.update(eligible[1:])
    candidates = [doc for doc in output if doc["doc_id"] in pool["doc_ids"]
                  and doc["doc_id"] not in blocked | duplicate_omitted and doc["references"]]
    # Existing protocol's 48-character / 0.60 containment clusters. They are
    # split groups, not labels to merge: similar texts can have different facts.
    spec = importlib.util.spec_from_file_location("arge_twins", inputs["twins"])
    twins = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(twins)
    pairs = twins.twin_pairs({doc["doc_id"]: doc["text"] for doc in candidates})
    clusters = twins.twin_clusters([doc["doc_id"] for doc in candidates], pairs)
    group_map = {oid: min(group) for group in clusters for oid in group}
    training_exclusions = []
    allowed = set(pool["doc_ids"])
    for doc in output:
        oid = doc["doc_id"]
        reasons = []
        if oid not in allowed:
            reasons.append("outside_frozen_leakage_screened_pool")
        if oid in blocked:
            reasons.append("unresolved_review_or_duplicate_label_conflict")
        if oid in duplicate_omitted:
            reasons.append("duplicate_document_text_and_targets")
        if not doc["references"]:
            reasons.append("empty_labels_not_verified_negative")
        if reasons:
            training_exclusions.append({"doc_id": oid, "reasons": reasons})
    gates = validate(processor, output, candidates, allowed, blocked)
    actions = Counter(record["action"] for record in row_audit)
    counts = {
        "source_documents": len(docs), "source_reference_rows": len(source_rows),
        "output_documents": len(output), "output_reference_rows": sum(len(doc["references"]) for doc in output),
        "empty_output_documents": sum(not doc["references"] for doc in output),
        "deduplicated_rows": actions["deduplicated"], "subsumed_law_only_rows": actions["subsumed_law_only"],
        "quarantined_source_rows": len(issues), "quarantine_reasons": dict(Counter(r["reason"] for r in issues)),
        "original_pending_rows": len(original_pending), "training_candidates": len(candidates),
        "original_pending_resolved": sum(r["decision"]["decision"] != "unresolved" for r in pending_resolution),
        "numberless_name_fallback_source_rows": sum(r["numberless_name_fallback"] for r in row_audit),
        "training_reference_rows": sum(len(doc["references"]) for doc in candidates),
        "training_excluded_documents": len(training_exclusions), "exact_duplicate_document_groups": len(exact),
        "conflicting_exact_duplicate_groups": len(conflicts), "duplicate_training_documents_omitted": len(duplicate_omitted),
        "near_duplicate_pairs": len(pairs), "training_split_groups": len(clusters),
        "normalized_or_relabelled_rows": sum(r["projected"] != {k: clean(r["original"].get(k)) for k in FIELDS} for r in row_audit),
        "law_only_output_rows": sum(not r["madde"] for d in output for r in d["references"]),
        "name_only_output_rows": sum(not r["kanun_no"] for d in output for r in d["references"]),
    }
    if sum(actions.values()) != len(source_rows) or actions["kept"] != counts["output_reference_rows"]:
        raise ValueError("Input/output row accounting failed")
    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = out.with_name(out.name + ".staging")
    if out.exists() or stage.exists():
        raise ValueError("Output/staging already exists; choose a NEW version path")
    stage.mkdir()

    def write_json(relative, value):
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    def write_jsonl(relative, values):
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            for value in values:
                stream.write(json_bytes(value))

    write_jsonl("documents.jsonl", output)
    write_jsonl("references.jsonl", [dict(r, document_id=d["doc_id"]) for d in output for r in d["references"]])
    for doc in output:
        write_json(f"validated/doc_{doc['doc_id']}.json", doc)
    write_jsonl("training/candidates.jsonl", candidates)
    instruction = ("Özelge metnindeki kanun referanslarını çıkar. Yalnız kanun_no, kanun_ad ve madde alanlarını kullan. "
                   "Kanun numarası bilinmiyorsa boş bırak ve metinde geçen kanun adını kullan. "
                   "Kanun numarası veya adı metinde bulunmalı. Madde belirtilmiyorsa maddeyi boş bırak. "
                   "Her kanun–madde referansını yalnız bir kez yaz. Fıkra, bent ve alıntı çıkarma. "
                   "Yalnız JSON dizisi döndür.")
    write_jsonl("training/sft.jsonl", [{"doc_id": d["doc_id"], "split_group": group_map[d["doc_id"]],
                                        "messages": [{"role": "system", "content": instruction},
                                                     {"role": "user", "content": d["text"]},
                                                     {"role": "assistant", "content": json.dumps(d["references"], ensure_ascii=False, separators=(",", ":"))}]}
                                       for d in candidates])
    write_json("training/split_groups.json", {"rule": {"shingle_chars": 48, "threshold": 0.60},
                                               "groups": [sorted(g) for g in clusters],
                                               "note": "No train/val/test split assigned. Keep each whole group in one split."})
    write_jsonl("review/row_lineage.jsonl", row_audit)
    write_jsonl("review/quarantine.jsonl", issues)
    write_jsonl("review/original_pending.jsonl", original_pending)
    write_jsonl("review/pending_resolution.jsonl", pending_resolution)
    write_jsonl("review/training_exclusions.jsonl", training_exclusions)
    write_json("review/duplicate_documents.json", {"exact_groups": exact, "conflicting_groups": conflicts,
                                                    "near_pairs": [[a,b,round(score,6)] for a,b,score in pairs]})
    write_json("QA.json", {"gates": gates, "actions": dict(actions), "counts": counts})
    manifest = {"schema_version": 1, "policy_id": "arge_law_article_only_2026_10_06_v1", "fields": list(FIELDS),
                "counts": counts, "inputs": locked,
                "policy": {"text": "HTML body only, NFKC, entities/HTML/whitespace normalized",
                           "grounding": "law-number wording OR canonical/alias law name in full document body",
                           "law_only": "keep only if same law has no article reference in the document",
                           "range": "preserve explicit ranges; do not expand nested subparts",
                           "identity": "law number, else normalized law name; plus canonical article",
                           "training": "frozen 1191-doc pool, unresolved/empty/conflicting/exact duplicate documents excluded",
                           "scope": "ARGE copy only; no journal, benchmark, model, or database changes"}}
    manifest["outputs"] = {str(path.relative_to(stage)): sha(path) for path in sorted(stage.rglob("*")) if path.is_file()}
    write_json("MANIFEST.json", manifest)
    # Verify persisted JSONL/schema and every checksum before publishing.
    persisted = [json.loads(line) for line in (stage / "documents.jsonl").read_text().splitlines()]
    if persisted != output or any(sha(stage / p) != digest for p,digest in manifest["outputs"].items()):
        raise ValueError("Persisted data/checksum verification failed")
    if any(sha(path) != locked[key]["sha256"] for key,path in inputs.items()):
        raise ValueError("An input changed during preprocessing")
    stage.rename(out)
    print(json.dumps({"output": str(out), "counts": counts, "gates": gates}, ensure_ascii=False, indent=2))
    return manifest


def validate(processor, output, candidates, allowed, blocked):
    for docs in (output, candidates):
        ids = [d["doc_id"] for d in docs]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate document in output")
        for doc in docs:
            refs = doc["references"]
            if any(set(r) != set(FIELDS) or any(not isinstance(v,str) for v in r.values()) for r in refs):
                raise ValueError("Unexpected/nested target fields")
            if any(not processor.grounding(r, doc["text"])["grounded"] for r in refs):
                raise ValueError(f"Ungrounded law: {doc['doc_id']}")
            keys = [processor.identity(r) for r in refs]
            if len(set(keys)) != len(keys):
                raise ValueError("Duplicate reference target")
            if processor.process(doc["doc_id"], refs, doc["text"])[0] != refs:
                raise ValueError("Projection/dedup is not idempotent")
    if any(d["doc_id"] not in allowed or d["doc_id"] in blocked or not d["references"] for d in candidates):
        raise ValueError("Unresolved or held-out document entered training")
    if exact_document_groups(candidates):
        raise ValueError("Duplicate document texts in training")
    return {key: "PASS" for key in ("schema_exactly_three_fields", "law_grounded_in_document",
                                    "no_duplicate_references", "no_duplicate_training_documents",
                                    "idempotent_preprocessing", "source_archive_matches_jsonl",
                                    "unresolved_documents_not_in_training", "frozen_pool_membership")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--dq-root", type=Path, default=DQ_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
