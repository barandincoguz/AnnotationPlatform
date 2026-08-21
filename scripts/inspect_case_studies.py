import json

with open("scripts/discrepancy_analysis_full.json", "r", encoding="utf-8") as f:
    data = json.load(f)

cases = data["case_study_candidates"]

print("=== SAMPLE HUMAN OMISSION CASE (Model Caught, Human Missed) ===")
for case in cases["human_omissions_sample"][:3]:
    print(f"\nDocument ID: {case['document_id']} | Difficulty: {case['difficulty']} | Words: {case['word_count']}")
    print(f"Human Refs Count: {case['human_ref_count']} | Model Refs Count: {case['model_ref_count']}")
    print("Model Extra Found:")
    for m in case["model_only_cores"]:
        print(f"  - Law {m['kanun_no']} Art {m['madde']} | Text: {m['sample'].get('source_text')}")
    print(f"Text Snippet: {case['text_preview'][:200]}...")

print("\n=== SAMPLE DETAIL MISMATCH CASE (Granularity Divergence) ===")
for case in cases["high_discrepancy_sample"][:3]:
    if case["detail_mismatches"]:
        print(f"\nDocument ID: {case['document_id']}")
        for dm in case["detail_mismatches"][:2]:
            print(f"  - Law {dm['kanun_no']} Art {dm['madde']}")
            print(f"    Human details: {dm['human_details']}")
            print(f"    Model details: {dm['model_details']}")
