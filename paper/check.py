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

# Pre-policy numbers that must NEVER appear (do not add to ALLOWED_NUMBERS to silence these).
# Task 6 will extend this dict for the 413 case.
FORBIDDEN_PATTERNS = {
}

# Numbers that are not merely absent from the allowlist but must never be added to it:
# the pre-policy bucket counts and transitions excluded by spec section 3. They are
# already blocked by the allowlist; this set only corrects the guidance in the message.
NEVER_ADD = {"111", "93", "231", "118", "1087", "1,087", "1180", "1,180", "19.58"}


def extract_text(path: Path, claims_only: bool = False) -> str:
    """Full document text, or only the claim-bearing text before the References heading.

    Number provenance applies to claims, not to citation metadata: reference entries
    legitimately carry volumes, issues, page ranges, arXiv IDs and DOIs that are not
    facts about this work and do not belong in the canonical facts table.
    """
    d = docx.Document(path)
    parts = []
    for p in d.paragraphs:
        if claims_only and p.text.strip().lower() == "references":
            break
        parts.append(p.text)
    for t in d.tables:
        for row in t.rows:
            parts.extend(c.text for c in row.cells)
    return "\n".join(parts)


def check_forbidden(text: str) -> list[str]:
    low = text.lower()
    out = [f"FORBIDDEN {term!r}: {why}" for term, why in FORBIDDEN.items()
           if term.lower() in low]
    out += [f"FORBIDDEN /{pat}/: {why}" for pat, why in FORBIDDEN_PATTERNS.items()
            if re.search(pat, text)]
    return out


def check_numbers(text: str) -> list[str]:
    """Every number outside a citation bracket must be in the allowlist."""
    stripped = re.sub(r"\[\d{1,2}\](?:\s*,\s*\[\d{1,2}\])*", " ", text)      # citations [1], [2]
    stripped = re.sub(r"\b(19|20|26)\d{2}\b", " ", stripped)                  # years
    stripped = re.sub(r"\b[IVX]+\.", " ", stripped)                           # roman headings
    stripped = re.sub(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{6,}\b", " ", stripped)   # hex hashes ONLY
    stripped = re.sub(r"\b\d+\.\d+\.\d+\b", " ", stripped)                    # versions 0.31.0
    stripped = re.sub(r"\d+\.?\d*\s*[eE]\s*[-−]?\d+", " ", stripped)     # 2.5e-5
    stripped = re.sub(r"\b[A-Za-z_]\w*(?:[._]\w+)+", " ", stripped)           # text_config, Qwen3.5
    bad = []
    for tok in re.findall(r"\d(?:[\d,]*\d)?(?:\.\d+)?", stripped):
        if tok not in ALLOWED_NUMBERS:
            if tok in NEVER_ADD:
                bad.append(f"FORBIDDEN NUMBER {tok!r} — pre-policy figure, must NEVER "
                           f"appear and must NEVER be added to ALLOWED_NUMBERS")
            else:
                bad.append(f"UNKNOWN NUMBER {tok!r} — add to spec section 5 first")
    return sorted(set(bad))


# Canonical routing figures, spec section 5.5.
BUCKET_CANON = {"GREEN": 342, "YELLOW": 211, "RED": 738, "QUARANTINE": 3}

# Every integer that may legitimately appear as a routing count, spec section 5.5.
# A number near a bucket name that is not one of these is a figure error.
ROUTING_FIGURES = set(BUCKET_CANON.values()) | {1294, 949}


def _snap(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen a slice outward so it never cuts through the middle of a number. Without this a
    +/-40 character window yields fragments like 42 out of 342 and flags them as foreign
    figures on correct content."""
    while start > 0 and (text[start - 1].isdigit() or text[start - 1] == ","):
        start -= 1
    while end < len(text) and (text[end].isdigit() or text[end] == ","):
        end += 1
    return start, end


def check_bucket_figures(text: str) -> list[str]:
    """Flag any integer appearing within forty characters of a bucket name that is not a
    legitimate routing figure. Catches an internally inconsistent figure set whose numbers
    are each allow-listed for some other reason.

    Non-counts are removed before candidates are extracted rather than filtered by size,
    because a size threshold silently misses a wrong count that happens to be small:
      - years;
      - section, figure, table, step and task references, including Roman numerals;
      - any number carrying a decimal point, which is a rate or a share, not a count;
      - any integer written as a percentage.
    """
    errs = []
    scrubbed = re.sub(r"\b(19|20|26)\d{2}\b", " ", text)
    scrubbed = re.sub(r"\b(?:section|sec\.|fig\.|figure|table|step|task)\s*[IVX\d]+",
                      " ", scrubbed, flags=re.I)
    scrubbed = re.sub(r"\d[\d,]*\.\d+", " ", scrubbed)
    scrubbed = re.sub(r"\b\d[\d,]*\s*%", " ", scrubbed)
    for name, canon in BUCKET_CANON.items():
        for m in re.finditer(rf"\b{name}\b", scrubbed, re.I):
            lo, hi = _snap(scrubbed, max(0, m.start() - 40), min(len(scrubbed), m.end() + 40))
            window = scrubbed[lo:hi]
            for tok in re.findall(r"\b\d[\d,]*\b", window):
                value = int(tok.replace(",", ""))
                if value not in ROUTING_FIGURES:
                    errs.append(
                        f"BUCKET FIGURE: {name} appears near {value}, which is not a "
                        f"legitimate routing figure (canonical count is {canon})"
                    )
    return sorted(set(errs))


def check_bucket_table_rows() -> list[str]:
    """In any table row whose first cell names a bucket, the first integer cell must be that
    bucket's canonical count. Safe to enforce strictly here because the label and its count
    are adjacent by construction — the same rule applied to prose false-positives on
    sentences that mention a bucket near an unrelated figure."""
    errs = []
    doc = docx.Document(DOCX)
    for ti, table in enumerate(doc.tables):
        for ri, row in enumerate(table.rows):
            cells = [c.text.strip() for c in row.cells]
            if not cells:
                continue
            for name, canon in BUCKET_CANON.items():
                if not re.search(rf"\b{name}\b", cells[0], re.I):
                    continue
                found = None
                for cell in cells[1:]:
                    m = re.fullmatch(r"(\d[\d,]*)", cell)
                    if m:
                        found = int(m.group(1).replace(",", ""))
                        break
                if found is not None and found != canon:
                    errs.append(
                        f"TABLE {ti + 1} row {ri + 1}: bucket {name} states {found}, "
                        f"canonical count is {canon}"
                    )
    return errs


def check_table_sums(text: str) -> list[str]:
    """Any table row whose first cell is 'Total' must equal the sum of the numeric rows
    above it, per column. Operates on the rendered document, not on constants."""
    errs = []
    doc = docx.Document(DOCX)
    for ti, table in enumerate(doc.tables):
        rows = [[c.text.strip() for c in r.cells] for r in table.rows]
        totals = [i for i, r in enumerate(rows) if r and r[0].lower().startswith("total")]
        for tr in totals:
            for col in range(1, len(rows[tr])):
                stated = _as_number(rows[tr][col])
                if stated is None:
                    continue
                above = [_as_number(r[col]) for r in rows[1:tr] if col < len(r)]
                above = [v for v in above if v is not None]
                if _is_count_column(rows, tr, col):
                    tol = 0.0
                else:
                    tol = min(0.05 * len(above) + 0.001, 0.25)
                if above and abs(sum(above) - stated) > tol:
                    errs.append(
                        f"TABLE {ti + 1} column {col}: rows sum to {sum(above)} "
                        f"but the Total row states {stated}"
                    )
    return errs


def _as_number(cell: str):
    m = re.fullmatch(r"(\d(?:[\d,]*\d)?(?:\.\d+)?)\s*%?", cell.strip())
    return float(m.group(1).replace(",", "")) if m else None


def _is_count_column(rows, tr, col) -> bool:
    """True when every cell above the Total row that parses as a number is a plain integer —
    no decimal point, no percent sign. Cells that are not numbers at all (blank, a dash) are
    ignored rather than disqualifying the column, which would silently relax it to the
    tolerance branch. Such a column must sum exactly."""
    cells = [r[col].strip() for r in rows[1:tr] if col < len(r) and r[col].strip()]
    numeric = [c for c in cells if _as_number(c) is not None]
    return bool(numeric) and all(re.fullmatch(r"\d[\d,]*", c) for c in numeric)


def check_checker_constants() -> list[str]:
    """Self-check of this file's own canonical constants. NOT a gate on the document —
    check_bucket_figures and check_table_sums are. Kept so a bad edit to the constants
    above screams instead of silently loosening the gates."""
    errs = []
    if sum(BUCKET_CANON.values()) != 1294:
        errs.append("BUCKET_CANON values do not sum to 1294")
    if BUCKET_CANON["YELLOW"] + BUCKET_CANON["RED"] != 949:
        errs.append("review load is not YELLOW + RED")
    if round(BUCKET_CANON["GREEN"] / 1294 * 100, 1) != 26.4:
        errs.append("26.4% does not follow from GREEN/1294")
    if 394 + 50 + 50 != 494 or 494 + 6 != 500:
        errs.append("canonical split constants are inconsistent")
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
    full = extract_text(DOCX)
    claims = extract_text(DOCX, claims_only=True)
    problems = (check_forbidden(full) + check_numbers(claims)
                + check_bucket_figures(claims) + check_bucket_table_rows()
                + check_table_sums(claims) + check_checker_constants()
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
