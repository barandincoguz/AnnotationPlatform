"""Verification gates for the IISEC paper. Exit 0 = pass, 1 = fail."""
import re
import sys
from pathlib import Path

import docx
import fitz

OUT = Path(__file__).parent / "out"
DOCX = OUT / "paper.docx"
PDF = OUT / "paper.pdf"
MAX_PAGES = 6

# Every numeric token permitted in the paper, from spec section 5.
ALLOWED_NUMBERS = {
    # corpus
    "17923", "17,923", "1437", "1,437", "1413", "1,413", "6840", "6,840", "14", "4.84",
    "577", "29.1", "6", "200", "0",
    # model
    "3.5", "9", "4", "8", "16", "20.0", "0.0", "1", "42", "2.5", "1.0", "1536", "256",
    "12288", "12,288", "8253", "8,253", "494", "4278", "4,278", "1003", "1,003", "0.94", "0.31.0",
    # model architecture (mlx-lm loader description, spec 5.2)
    "32", "27", "4096", "4,096", "248320", "248,320", "64",
    # splits
    "500", "394", "50", "17423", "17,423", "38",
    # results
    "0.789", "0.861", "0.728", "13", "26.0", "0.805", "0.8525", "0.7625", "47", "47.0", "100",
    # routing
    "1294", "1,294", "342", "211", "738", "3", "949", "26.4", "16.3", "57.0", "0.2", "73.3", "100",
    # runtime
    "7.63", "6.21", "13.26", "17.29", "24.62", "36.83", "9872", "9,872", "10964", "10,964",
    "2", "45", "11", "12", "3.05",
    # years, citation numbers and ordinals are handled separately
}

# Terms that must never appear, mapped to the reason.
FORBIDDEN = {
    "harness": "quality harness is out of scope (spec 3)",
    "jaccard": "inter-annotator Jaccard is out of scope (spec 3)",
    "kappa": "chance-corrected agreement is out of scope (spec 3)",
    "krippendorff": "out of scope (spec 3)",
    "gamif": "gamification is out of scope (spec 3)",
    "review_kept": "out of scope (spec 3)",
    "outbox": "CDC mirror is out of scope (spec 3)",
    "413": "VUK 213/413 policy is excluded by user decision (spec 3)",
    "19.58": "pre-policy comparison is excluded (spec 3)",
    "1,180": "pre-policy review load is excluded (spec 3)",
    "1180": "pre-policy review load is excluded (spec 3)",
    "1,087": "pre-policy bucket count is excluded (spec 3)",
    "1087": "pre-policy bucket count is excluded (spec 3)",
    # residual template boilerplate
    "use style": "template guidance text not removed",
    "Heading 1)": "template guidance text not removed",
    "IEEE conference templates contain guidance text": "template warning not removed",
    "Identify applicable funding agency": "sponsor placeholder not removed",
    "G. Eason": "template example reference not removed",
    "K. Elissa": "template example reference not removed",
}


def extract_text(path: Path) -> str:
    d = docx.Document(path)
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.extend(c.text for c in row.cells)
    return "\n".join(parts)


def check_forbidden(text: str) -> list[str]:
    low = text.lower()
    return [f"FORBIDDEN {term!r}: {why}" for term, why in FORBIDDEN.items()
            if term.lower() in low]


def check_numbers(text: str) -> list[str]:
    """Every number outside a citation bracket must be in the allowlist."""
    stripped = re.sub(r"\[\d+(?:\]\s*,\s*\[?\d+)*\]", " ", text)  # drop [1], [1], [2]
    stripped = re.sub(r"\b(19|20|26)\d{2}\b", " ", stripped)      # drop years
    stripped = re.sub(r"\b[IVX]+\.", " ", stripped)               # drop roman headings
    stripped = re.sub(r"\b[0-9a-f]{6,}\b", " ", stripped)         # drop revision hashes (938d891)
    stripped = re.sub(r"\b\d+\.\d+\.\d+\b", " ", stripped)        # drop versions (0.31.0)
    stripped = re.sub(r"\d+\.?\d*\s*[eE]\s*[-−]?\d+", " ", stripped)  # drop 2.5e-5, 1.0e-5
    stripped = re.sub(r"[A-Za-z_]+\d[\w.]*|\w*_\w+", " ", stripped)  # drop identifiers (Qwen3_5..., text_config)
    bad = []
    for tok in re.findall(r"\d[\d,]*\.?\d*", stripped):
        if tok.rstrip(".") not in ALLOWED_NUMBERS:
            bad.append(f"UNKNOWN NUMBER {tok!r} — add to spec section 5 first")
    return sorted(set(bad))


def check_arithmetic() -> list[str]:
    errs = []
    if 342 + 211 + 738 + 3 != 1294:
        errs.append("bucket counts do not sum to 1294")
    if 211 + 738 != 949:
        errs.append("review load is not YELLOW + RED")
    if round(342 / 1294 * 100, 1) != 26.4:
        errs.append("26.4% does not follow from 342/1294")
    if 394 + 50 + 50 != 494:
        errs.append("split does not sum to 494")
    if 494 + 6 != 500:
        errs.append("canonical set does not sum to 500")
    return errs


def check_pages() -> list[str]:
    d = fitz.open(PDF)
    if d.page_count > MAX_PAGES:
        return [f"PAGE LIMIT: {d.page_count} pages, maximum is {MAX_PAGES}"]
    return []


def check_no_page_numbers() -> list[str]:
    d = docx.Document(DOCX)
    errs = []
    for i, sec in enumerate(d.sections):
        for footer in (sec.footer, sec.first_page_footer):
            if footer is not None and footer.paragraphs:
                if any(p.text.strip() for p in footer.paragraphs):
                    errs.append(f"section {i}: footer is not empty")
                if footer._element.xpath('.//w:fldSimple | .//w:instrText'):
                    errs.append(f"section {i}: footer contains a field (page number?)")
    return errs


def main() -> int:
    if not DOCX.exists() or not PDF.exists():
        print("FAIL: run paper/build.py first")
        return 1
    text = extract_text(DOCX)
    problems = (check_forbidden(text) + check_numbers(text) + check_arithmetic()
                + check_pages() + check_no_page_numbers())
    if problems:
        print(f"FAIL — {len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        return 1
    print(f"PASS — {fitz.open(PDF).page_count} pages, all gates clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
