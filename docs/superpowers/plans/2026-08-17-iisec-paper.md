# IISEC 2027 Paper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a 6-page IEEE-format conference paper (`.docx` + `.pdf`) describing the LLM cross-check mechanism added to the tax-ruling annotation platform, for IISEC 2027.

**Architecture:** Prose lives in a plain Markdown source. A builder script strips the conference template's boilerplate, injects the prose into the template's own existing styles and section structure, and converts to PDF with headless LibreOffice. A checker script enforces page count, number provenance, forbidden-topic exclusion, arithmetic consistency, and template-residue removal. Format compliance is inherited from the official template rather than reconstructed.

**Tech Stack:** Python 3.11+, `python-docx` (installed), `reportlab` (installed, for Figure 1), `PyMuPDF`/`fitz` (installed, for page count and raster rendering), LibreOffice headless at `/Applications/LibreOffice.app/Contents/MacOS/soffice` (installed). No LaTeX. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-17-iisec-paper-design.md`

## Global Constraints

- Page limit: **6 pages maximum, including references.** Hard gate.
- Language: English.
- Template: `iisec_template.docx` at repo root. Never edit it in place — always copy.
- A4 (21.0 × 29.7 cm), two-column body, single-column title block, Times New Roman. Inherit all of this from the template's styles; do not set fonts or geometry manually.
- **No page numbers.** No template guidance text may remain.
- In-text citations: bracketed numeric `[1]`, consecutive.
- Every number in the paper must appear in the spec's §5 canonical facts tables. No new numbers without adding them to the spec first.
- Forbidden topics (spec §3): the quality harness and R01–R17 rubric, the 979→9 collapse, the n=400 audit and its 18%/0.5% figures, inter-annotator Jaccard, gamification, the CDC mirror, document locking, the training/quiz gate, cross-team coordination, per-annotator rankings, **and the VUK 213/413 target policy including all pre-policy bucket counts (111, 93, 1087, 1180, 231, 118, 19.58)**.
- Claim discipline (spec §4): "keeping annotators aligned" is design intent only, never a result. Canonical Test-50 metrics are *accuracy/F1*; External-100 metrics are *human-annotator agreement*, never accuracy. The development model (F1 0.789) and the deployed model are different models and must never be conflated. Disclose that External-100 also served for checkpoint selection.
- Headline result: 342 of 1,294 documents (26.4%) cleared as concordant; expert review load 1,294 → 949, a 26.4% reduction.

## File Structure

| File | Responsibility |
| --- | --- |
| `paper/content.md` | All prose and reference entries, delimited by section markers. The only file a writer edits. |
| `paper/build.py` | Copies the template, deletes boilerplate, injects `content.md` into template styles, inserts Figure 1 and Tables I–III, converts to PDF. |
| `paper/check.py` | Verification gates: page count, number allowlist, forbidden terms, arithmetic, template residue, footer emptiness. |
| `paper/fig1.py` | Generates the architecture figure as a vector PDF, rasterized to 300 dpi PNG. |
| `paper/out/` | Build artifacts: `paper.docx`, `paper.pdf`, `fig1.png`. Git-ignored. |

Four source files, one responsibility each. Prose is separated from document plumbing so it can be edited and diffed as text.

---

### Task 1: Build pipeline skeleton

Riskiest task technically, so it goes first. Nothing about the paper's content is decided here — the deliverable is a template-faithful A4 two-column PDF containing placeholder prose.

**Files:**
- Create: `paper/build.py`
- Create: `paper/content.md`
- Create: `paper/.gitignore`

**Interfaces:**
- Produces: `build() -> tuple[Path, Path]` writing `paper/out/paper.docx` and `paper/out/paper.pdf`; `parse_content(path) -> list[tuple[kind, label, text]]`; `strip_template_content(doc) -> list` returning the five structural anchors; **`para_before(doc, anchor, style, text="")`** — the single paragraph-insertion helper that all later tasks build on; `render(blocks, doc, anchors)`; `docx_to_pdf(docx_path, outdir) -> Path`.

- [ ] **Step 1: Confirm the template's structure — already surveyed, verify it still holds**

The survey below was run against `iisec_template.docx` on 2026-08-17. Re-run it and confirm the numbers match before writing code; if they differ, the template changed and the anchor indices in Step 3 must be re-derived.

```bash
cd /Users/barandincoguz/Desktop/AnnotationProgram
python3 - <<'PY'
import docx
d = docx.Document('iisec_template.docx')
NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
for i, ch in enumerate(d.element.body):
    sect = ch.find(f'{NS}pPr/{NS}sectPr')
    if sect is None and not ch.tag.endswith('}sectPr'):
        continue
    c = sect.find(f'{NS}cols') if sect is not None else None
    print(i, ch.tag.replace(NS, ''), 'cols=', c.get(f'{NS}num', '1') if c is not None else '-')
print('total body children:', len(d.element.body))
PY
```

Expected, verbatim: body child `3` is a paragraph with `cols=1`, `8` and `9` are paragraphs with `cols=3`, `85` is a paragraph with `cols=2`, `87` is the body-level `sectPr`, and there are 88 body children.

**This is the critical structural fact of the whole task.** The template's column layout is encoded in `w:pPr/w:sectPr` elements *inside ordinary paragraphs*, not in separate section objects. Deleting those paragraphs collapses the single-column title block, the three-column author block and the two-column body into one section, and the title then typesets inside a narrow body column. They must be preserved and used as insertion anchors.

Verified style names — use these exact strings, they are not guesses:

`'paper title'`, `'paper subtitle'`, `'Author'`, `'Affiliation'`, `'Abstract'`, `'Keywords'`, `'Heading 1'` through `'Heading 5'` (capital H), `'Body Text'`, `'bullet list'`, `'figure caption'`, `'table head'`, `'table col head'`, `'table copy'`, `'table footnote'`, `'references'`, `'equation'`, `'sponsors'`, `'Normal Table'`.

**There is no `'Table Grid'` style in this template.** Do not reference it.

- [ ] **Step 2: Write `paper/content.md` with placeholder prose**

One marker per section. Markers are the contract between `content.md` and `build.py`.

```markdown
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

<!-- H1: Conclusion -->
Placeholder conclusion body paragraph.

<!-- REFERENCES -->
A. Author, "Placeholder reference title," in Proc. Some Conf., 2020.
```

- [ ] **Step 3: Write `paper/build.py`**

```python
"""Build the IISEC paper from content.md into the conference template."""
import re
import shutil
import subprocess
from pathlib import Path

import docx

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "iisec_template.docx"
CONTENT = Path(__file__).parent / "content.md"
OUT = Path(__file__).parent / "out"
SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Style names verified against the template in Step 1. Exact strings.
STYLE_TITLE = "paper title"
STYLE_AUTHOR = "Author"
STYLE_ABSTRACT = "Abstract"
STYLE_KEYWORDS = "Keywords"
STYLE_H1 = "Heading 1"
STYLE_H2 = "Heading 2"
STYLE_H5 = "Heading 5"
STYLE_BODY = "Body Text"
STYLE_REFS = "references"
STYLE_FIGCAP = "figure caption"
STYLE_TABHEAD = "table head"
STYLE_TABCOLHEAD = "table col head"
STYLE_TABCOPY = "table copy"


def parse_content(path: Path) -> list[tuple[str, str, str]]:
    """Return [(kind, label, text)] where kind is TITLE/ABSTRACT/KEYWORDS/H1/H2/REFERENCES/BODY."""
    blocks: list[tuple[str, str, str]] = []
    # All markers are declared here once, including FIGURE and TABLE which Tasks 3 and 4 use.
    # Declaring them up front means neither task has to edit this pattern.
    marker = re.compile(
        r"^<!--\s*(TITLE|AUTHORS|ABSTRACT|KEYWORDS|REFERENCES|FIGURE|TABLE|H1|H2):?\s*(.*?)\s*-->$"
    )
    kind, label, buf = None, "", []

    def flush():
        if kind is None:
            return
        body = "\n".join(buf).strip()
        blocks.append((kind, label, body))

    for line in path.read_text(encoding="utf-8").splitlines():
        m = marker.match(line.strip())
        if m:
            flush()
            kind, label, buf = m.group(1), m.group(2), []
        else:
            buf.append(line)
    flush()
    return blocks


def strip_template_content(doc: docx.Document) -> list:
    """Delete the template's boilerplate while PRESERVING the paragraphs whose pPr carries a
    sectPr. Those paragraphs encode the column layout (1-col title, 3-col author, 2-col body);
    deleting them collapses the document into a single section and the title typesets inside a
    narrow body column. Their runs are emptied so no template text survives.

    Returns the surviving structural anchors in document order:
      [0] paragraph ending the 1-column title section
      [1] paragraph ending the first 3-column author section
      [2] paragraph ending the duplicate 3-column section
      [3] paragraph ending the 2-column body section
      [4] the body-level sectPr element
    """
    body = doc.element.body
    anchors = []
    for child in list(body):
        if child.tag.endswith("}sectPr"):
            anchors.append(child)
            continue
        if child.find(f"{NS}pPr/{NS}sectPr") is not None:
            for run in child.findall(f"{NS}r"):
                child.remove(run)
            anchors.append(child)
            continue
        body.remove(child)
    if len(anchors) != 5:
        raise RuntimeError(f"expected 5 structural anchors, found {len(anchors)} — template changed")
    return anchors


def para_before(doc: docx.Document, anchor, style: str, text: str = ""):
    """Create a paragraph and move it immediately before `anchor`, so it lands in the section
    that `anchor` terminates. python-docx can only append, so we append then relocate."""
    p = doc.add_paragraph(style=style)
    if text:
        p.add_run(text)
    anchor.addprevious(p._element)
    return p


def render(blocks, doc: docx.Document, anchors: list) -> None:
    title_anchor, author_anchor, body_anchor = anchors[0], anchors[1], anchors[3]
    for kind, label, text in blocks:
        if kind == "TITLE":
            para_before(doc, title_anchor, STYLE_TITLE, text)
        elif kind == "AUTHORS":
            for line in [l for l in text.splitlines() if l.strip()]:
                para_before(doc, author_anchor, STYLE_AUTHOR, line.strip())
        elif kind == "ABSTRACT":
            para_before(doc, body_anchor, STYLE_ABSTRACT, f"Abstract—{text}")
        elif kind == "KEYWORDS":
            para_before(doc, body_anchor, STYLE_KEYWORDS, f"Keywords—{text}")
        elif kind in ("H1", "H2"):
            para_before(doc, body_anchor, STYLE_H1 if kind == "H1" else STYLE_H2, label)
            for para in [p for p in text.split("\n\n") if p.strip()]:
                para_before(doc, body_anchor, STYLE_BODY, para.strip())
        elif kind == "REFERENCES":
            para_before(doc, body_anchor, STYLE_H5, "References")
            for entry in [l for l in text.splitlines() if l.strip()]:
                para_before(doc, body_anchor, STYLE_REFS, entry.strip())


def docx_to_pdf(docx_path: Path, outdir: Path) -> Path:
    """Convert with an isolated LibreOffice profile so a running GUI instance cannot block us."""
    subprocess.run(
        [SOFFICE, "-env:UserInstallation=file:///tmp/lo_iisec_profile",
         "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(docx_path)],
        check=True, capture_output=True,
    )
    pdf = outdir / (docx_path.stem + ".pdf")
    if not pdf.exists():
        raise RuntimeError(f"LibreOffice produced no PDF at {pdf}")
    return pdf


def build() -> tuple[Path, Path]:
    OUT.mkdir(exist_ok=True)
    work = OUT / "paper.docx"
    shutil.copy(TEMPLATE, work)
    doc = docx.Document(work)
    anchors = strip_template_content(doc)
    render(parse_content(CONTENT), doc, anchors)
    doc.save(work)
    pdf = docx_to_pdf(work, OUT)
    return work, pdf


if __name__ == "__main__":
    d, p = build()
    print(f"docx: {d}\npdf:  {p}")
```

- [ ] **Step 4: Write `paper/.gitignore`**

```
out/
```

- [ ] **Step 5: Run the build and verify geometry**

Run: `cd /Users/barandincoguz/Desktop/AnnotationProgram && python3 paper/build.py`
Expected: prints both paths, no traceback.

Then verify the output is A4 and the body is genuinely two-column:

```bash
python3 - <<'PY'
import fitz
d = fitz.open('paper/out/paper.pdf')
print('pages:', d.page_count)
p = d[0]
print('size pt:', round(p.rect.width, 1), round(p.rect.height, 1), '(A4 = 595.3 x 841.9)')
for b in p.get_text('blocks'):
    print(f'  x0={b[0]:6.1f} x1={b[2]:6.1f} w={b[2]-b[0]:6.1f} | {b[4][:48]!r}')
PY
```

Expected, and all three must hold:
1. Page size is A4 (595.3 × 841.9 pt).
2. The **title** is not trapped inside a body column. Note that `get_text('blocks')` reports the *text extent*, not the frame width, so a short title legitimately measures less than the column it sits in. The correct criterion is therefore: the title's text extent exceeds the two-column text width (about 243 pt), which is impossible unless it sits in the single-column section. For a stronger check, read the available width directly from the section XML rather than inferring it from glyph extent.
3. The **body** blocks fall into two distinct left-edge clusters roughly 260 pt apart, confirming the two-column section survived.

`strip_template_content` raises if it does not find exactly 5 anchors, so a structural loss fails loudly rather than producing a silently mislaid title.

- [ ] **Step 6: Commit**

```bash
git add paper/build.py paper/content.md paper/.gitignore
git commit -m "build: add IISEC paper build pipeline (docx template -> pdf)"
```

---

### Task 2: Verification gates

A checker that fails loudly. This is what keeps the paper honest across many editing rounds; write it before any real prose exists so the prose is never unchecked.

**Files:**
- Create: `paper/check.py`

**Interfaces:**
- Consumes: the build artifacts `paper/out/paper.docx` and `paper/out/paper.pdf` only. `check.py` does **not** import `build.py` — it reads the artifacts from disk so it can be run standalone.
- Produces: `main() -> int` exit code 0 pass / 1 fail; `extract_text(docx_path) -> str`; `ALLOWED_NUMBERS: set[str]`; `FORBIDDEN: dict[str, str]`. Tasks 5 and 6 reuse `extract_text` for their terminology checks.

- [ ] **Step 1: Write `paper/check.py`**

> **Superseded in part by fix round 1.** The code below was implemented as written and then corrected, because the review proved two of its gates silently passed content they are named to catch: the hex-hash strip `\b[0-9a-f]{6,}\b` also removes every run of six or more *decimal* digits (`0-9` is a subset of `[0-9a-f]`), and `check_arithmetic()` compares hardcoded literals to each other rather than to anything in the document. Four smaller defects followed: the citation strip removed any bracketed number, the identifier strip removed digits glued to a letter, the token pattern captured trailing commas (breaking on the spec's own `12,288,` phrasing), and four of the seven forbidden pre-policy numbers had no explicit entry.
>
> **The authoritative corrected code is `.superpowers/sdd/2026-08-17-iisec-paper/task-2-fix-1.md`**, which replaces `check_numbers`, replaces `check_arithmetic` with `check_bucket_figures` and `check_table_sums` (both read the rendered document) plus an honestly renamed `check_checker_constants`, adds `FORBIDDEN_PATTERNS`, and rewires `main`. Read the code below for context, but implement the fix file.

```python
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
```

- [ ] **Step 2: Prove the checker catches violations — seed each class of failure**

Append the following to `paper/content.md` temporarily:

```markdown
<!-- H1: Seeded Failures -->
We computed a Jaccard agreement of 0.679 and applied the 213/413 policy, reducing load by 19.58%.
```

Run: `python3 paper/build.py && python3 paper/check.py`
Expected: FAIL, listing forbidden `jaccard`, forbidden `413`, forbidden `19.58`, and unknown numbers `0.679`.

- [ ] **Step 3: Remove the seeded failures and confirm the checker passes**

Delete the `Seeded Failures` block from `content.md`.
Run: `python3 paper/build.py && python3 paper/check.py`
Expected: `PASS — N pages, all gates clear`

- [ ] **Step 4: Commit**

```bash
git add paper/check.py paper/content.md
git commit -m "test: add paper verification gates (pages, numbers, forbidden topics, arithmetic)"
```

---

### Task 3: Figure 1 — architecture diagram

**Files:**
- Create: `paper/fig1.py`
- Modify: `paper/build.py` (insert the figure and its caption)

**Interfaces:**
- Consumes: `build.para_before(doc, anchor, style, text)` and the `STYLE_FIGCAP` constant, both delivered by Task 1. There is no `add_paragraph` function — Task 1's insertion helper is `para_before`.
- Produces: `paper/out/fig1.png` at 300 dpi; `build.insert_figure(doc, anchor, png_path, caption, width_pt)`

- [ ] **Step 1: Write `paper/fig1.py`**

Boxes and arrows only, no colour, 8 pt Times labels per the template's figure-label rule. Single-column width: the body column is about 8.9 cm ≈ 252 pt.

```python
"""Generate Figure 1 (architecture) as a 300 dpi PNG sized for one IEEE column."""
from pathlib import Path

import fitz
from reportlab.lib.colors import black, white
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "out"
W, H = 252, 300  # points; 252 pt is one IEEE column


def draw(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=(W, H))
    c.setFont("Times-Roman", 8)
    c.setLineWidth(0.6)

    def box(x, y, w, h, lines):
        c.setFillColor(white)
        c.rect(x, y, w, h, stroke=1, fill=1)
        c.setFillColor(black)
        for i, line in enumerate(lines):
            c.drawCentredString(x + w / 2, y + h - 11 - i * 9, line)

    def arrow(x1, y1, x2, y2, label=""):
        c.line(x1, y1, x2, y2)
        c.line(x2, y2, x2 - 3, y2 + 4)
        c.line(x2, y2, x2 + 3, y2 + 4)
        if label:
            c.drawString(x2 + 5, (y1 + y2) / 2, label)

    box(6, 252, 110, 34, ["Annotation platform", "(human annotator)"])
    box(136, 252, 110, 34, ["Background LLM", "worker (local)"])
    box(6, 196, 240, 30, ["Comparison: legal-key alignment", "+ verbatim-quote grounding"])
    box(6, 120, 54, 26, ["GREEN"])
    box(68, 120, 54, 26, ["YELLOW"])
    box(130, 120, 54, 26, ["RED"])
    box(192, 120, 54, 26, ["QUAR."])
    box(6, 56, 110, 30, ["Cleared", "(no review)"])
    box(136, 56, 110, 30, ["Expert review", "+ annotator warning"])

    arrow(61, 252, 61, 226)
    arrow(191, 252, 191, 226)
    arrow(126, 196, 126, 146)
    arrow(33, 120, 61, 86)
    arrow(157, 120, 191, 86)
    arrow(95, 120, 191, 86)
    c.save()


def main() -> Path:
    OUT.mkdir(exist_ok=True)
    pdf = OUT / "fig1.pdf"
    png = OUT / "fig1.png"
    draw(pdf)
    page = fitz.open(pdf)[0]
    page.get_pixmap(dpi=300).save(png)
    return png


if __name__ == "__main__":
    print(main())
```

- [ ] **Step 2: Run it and confirm the raster resolution**

Run: `python3 paper/fig1.py`
Then: `python3 -c "import fitz; p=fitz.open('paper/out/fig1.png'); print(p[0].rect)"`
Expected: a PNG whose pixel dimensions are roughly 252/72×300 ≈ 1050 px wide, i.e. genuinely 300 dpi at column width.

- [ ] **Step 3: Add `insert_figure` to `build.py`**

Insert after the `para_before` helper:

Also make `render()` fail loudly on an unrecognized marker kind instead of silently dropping it — a mistyped marker currently vanishes from the paper with no error. Add as the final branch:

```python
        else:
            raise ValueError(f"unknown content marker: {kind!r}")
```

And correct `parse_content`'s docstring, which lists a `BODY` kind that no marker produces.

```python
from docx.shared import Pt


def insert_figure(doc, anchor, png_path, caption: str, width_pt: float = 252):
    p = doc.add_paragraph()
    p.add_run().add_picture(str(png_path), width=Pt(width_pt))
    anchor.addprevious(p._element)
    para_before(doc, anchor, STYLE_FIGCAP, caption)
```

And extend `render()` with a marker branch:

```python
        elif kind == "FIGURE":
            insert_figure(doc, body_anchor, OUT / "fig1.png", text)
```

The `FIGURE` marker is already in `parse_content`'s pattern from Task 1 — do not edit the regex.

- [ ] **Step 4: Reference the figure from `content.md`**

```markdown
<!-- FIGURE -->
Cross-check mechanism: the annotator's completed extraction and the model's independent extraction are aligned and routed into four outcome buckets.
```

- [ ] **Step 5: Build and check**

Run: `python3 paper/fig1.py && python3 paper/build.py && python3 paper/check.py`
Expected: PASS, and the figure appears in `paper/out/paper.pdf` with an auto-numbered "Fig. 1." caption.

- [ ] **Step 6: Commit**

```bash
git add paper/fig1.py paper/build.py paper/content.md
git commit -m "feat: add Figure 1 architecture diagram"
```

---

### Task 4: Tables I–III

**Files:**
- Modify: `paper/build.py`

**Interfaces:**
- Consumes: `build.para_before(doc, anchor, style, text)` and the `STYLE_TABHEAD`, `STYLE_TABCOLHEAD`, `STYLE_TABCOPY` constants, all delivered by Task 1. There is no `add_paragraph` function.
- Produces: `build.insert_table(doc, caption, header, rows)`

- [ ] **Step 1: Add `insert_table` to `build.py`**

The template has **no `'Table Grid'` style** — referencing it raises `KeyError`. Use `'Normal Table'` and style the cell paragraphs with the template's own `'table col head'` and `'table copy'` styles.

```python
def insert_table(doc, anchor, caption: str, header: list[str], rows: list[list[str]]):
    para_before(doc, anchor, STYLE_TABHEAD, caption)
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Normal Table"
    for cell, name in zip(t.rows[0].cells, header):
        cell.paragraphs[0].style = doc.styles[STYLE_TABCOLHEAD]
        cell.paragraphs[0].add_run(name)
    for row in rows:
        for cell, value in zip(t.add_row().cells, row):
            cell.paragraphs[0].style = doc.styles[STYLE_TABCOPY]
            cell.paragraphs[0].add_run(value)
    anchor.addprevious(t._element)
    return t
```

- [ ] **Step 2: Add the `TABLE` branch to `render`**

The `TABLE` marker is already in `parse_content`'s pattern from Task 1 — do not edit the regex. Table content in `content.md` uses pipe rows; the first line is the caption and the next row is the header.

```python
        elif kind == "TABLE":
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            grid = [[c.strip() for c in l.strip("|").split("|")] for l in lines[1:]]
            insert_table(doc, body_anchor, lines[0], grid[0], grid[1:])
```

- [ ] **Step 3: Add the three tables to `content.md`**

Content is copied verbatim from spec §5.2, §5.4 and §5.5. Table III is mandatory; Table I is the first to be cut if the page budget is tight.

```markdown
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
```

- [ ] **Step 4: Build and check**

Run: `python3 paper/build.py && python3 paper/check.py`
Expected: PASS. The arithmetic gate confirms 342 + 211 + 738 + 3 = 1294 and 211 + 738 = 949. Confirm captions render as "TABLE I."–"TABLE III." in the PDF.

- [ ] **Step 5: Commit**

```bash
git add paper/build.py paper/content.md
git commit -m "feat: add Tables I-III"
```

---

### Task 5: Sections III, IV, V — the technical core

Write the core before the framing so the introduction promises exactly what the paper delivers. Target 3.90 pages for these three sections (spec §6).

**Files:**
- Modify: `paper/content.md`

- [ ] **Step 1: Write Section III, "Task and Platform" (0.70 p)**

Content, from spec §5.1: the domain (Turkish tax rulings issued by the Revenue Administration, publicly available); the extraction task; the six-field schema with one worked example showing a law number, article, paragraph, subparagraph and the verbatim quote; corpus figures — 17,923-document pool, 1,437 annotated, 6,840 extracted references, 14 annotators, 4.84 references per document, mean 577 words per document; one sentence on the platform stack. No architecture depth, no workflow machinery.

- [ ] **Step 2: Write Section IV, "The LLM Cross-Check Mechanism" (1.50 p)**

Five subsections per spec §6-IV. A: model and adaptation, citing the model, LoRA and QLoRA references, stressing that adaptation used 494 adjudicated documents and one workstation. **Use the approved loader wording recorded in spec §8** — it pre-empts the reviewer who opens the model page and sees a multimodal checkpoint: upstream Qwen3.5 ships unified weights, `mlx-lm` builds only the 32-layer text backbone and discards `vision_tower` during load-time sanitization, so LoRA and inference run purely over the language pathway. Keep the intermediate dimension (12,288) and the inference context length (12,288) in separate sentences — they are unrelated quantities that share a value. B: constrained JSON output, the empty array for negatives, markdown-fence stripping, deterministic prefix salvage on repetition, verbatim-quote enforcement. C: comparison on the legal key plus quote grounding, and the four buckets — **no mention of the target policy**. D: the asynchronous worker, justified by the measured latency distribution (mean 7.63 s, p50 6.21 s, p90 13.26 s, p99 24.62 s), Figure 1 placed here. E: warnings rather than pre-filling, citing the anchoring-bias references and acknowledging the contrary result.

- [ ] **Step 3: Write Section V, "Evaluation" (1.70 p)**

Four subsections. A: the split, using the spec's summary sentence — 500 canonical documents partitioned into 394 training, 50 validation and 50 sealed test, excluding 6 few-shot exemplars; the sealed test opened once; leakage controls including the 38 excluded documents and zero split intersection. B: Table II with both caveats — the development and deployed models are different, and the external set also served for checkpoint selection so its figure is not an unbiased estimate. C: Table III and the headline — 342 documents cleared, review load 1,294 → 949, a 26.4% reduction. Most space goes here. D: runtime, from spec §5.6, in prose.

- [ ] **Step 4: Build, check, and record the page count**

Run: `python3 paper/build.py && python3 paper/check.py`
Expected: PASS. Note the page count; over 6 at this stage is acceptable and is resolved in Task 7.

- [ ] **Step 5: Verify terminology discipline by hand**

```bash
python3 -c "
import sys; sys.path.insert(0,'paper')
from check import extract_text
t = extract_text(__import__('pathlib').Path('paper/out/paper.docx'))
import re
for m in re.finditer(r'[^.]*\b(accuracy|accurate)\b[^.]*\.', t, re.I):
    print('ACCURACY SENTENCE:', m.group(0).strip()[:200])
"
```

Expected: no sentence uses "accuracy" for the External-100 result. Every such sentence must refer to the canonical sealed test or to the task in general.

- [ ] **Step 6: Commit**

```bash
git add paper/content.md
git commit -m "docs: draft sections III-V (task, mechanism, evaluation)"
```

---

### Task 6: Sections I, II, VI, VII and the reference list

**Files:**
- Modify: `paper/content.md`

- [ ] **Step 1: Write Section I, "Introduction" (0.75 p)**

Why expert legal annotation is expensive and why manual quality control does not scale; the Turkish legal NLP gap (a Turkish legal NER study and a domain language-model preprint exist; no Turkish tax-law NLP work was found); data sovereignty as motivation for on-premise inference; the contribution paragraph ending in the headline numbers; a one-sentence roadmap.

- [ ] **Step 2: Write Section II, "Related Work" (0.45 p)**

Four compressed threads per spec §6-II, using references 1–13 from spec §8. Cite the contrary evidence (Lingren et al.) explicitly in the pre-annotation thread and the optimistic baseline (Gilardi et al.) in the LLM-annotation thread.

- [ ] **Step 3: Write Section VI, "Discussion and Limitations" (0.40 p)**

Concordance with a single annotator is not correctness; a shared systematic error passes unflagged in the GREEN bucket; recall of 0.728–0.7625 means citations are missed and completeness cannot be certified; the deployed model has no unseen-canonical estimate; single domain, language and institution; and — stated plainly as the primary limitation — **no measurement of behavioural effect on annotators**, with a verification pass over flagged divergences named as the next step.

- [ ] **Step 4: Write Section VII, "Conclusion" (0.15 p)** and the reference list

Reference entries are copied verbatim from spec §8 in IEEE format, renumbered consecutively in order of first citation. Use the verified strings for the model, MLX, LoRA (ICLR 2022) and QLoRA (NeurIPS 2023). Do not cite the Qwen3.5-Omni technical report. Do not invent entries for doccano or Label Studio.

- [ ] **Step 5: Harden the `413` forbidden-term gate before adding the references**

`check.py`'s `FORBIDDEN` dict matches bare substrings, and reference 7 (Lingren et al., *JAMIA* 21(3):**406–413**, 2014) legitimately contains `413`. Adding the reference list as-is fails the gate on correct content, and the naive escape — deleting the entry — would remove the guard against the excluded target policy entirely.

Give `FORBIDDEN` regex support and target the policy mention rather than the digits. In `check.py`, add alongside `FORBIDDEN`:

```python
# Entries matched as regexes rather than plain substrings, for terms whose bare
# digits collide with legitimate content (e.g. a reference page range 406-413).
FORBIDDEN_PATTERNS = {
    r"\b213\s*/\s*413\b": "VUK 213/413 policy is excluded by user decision (spec 3)",
    r"\b(?:VUK|Article|article|madde)\s*413\b": "VUK 413 provision is excluded (spec 3)",
}
```

Remove the plain `"413"` entry from `FORBIDDEN`, and extend `check_forbidden`:

```python
def check_forbidden(text: str) -> list[str]:
    low = text.lower()
    out = [f"FORBIDDEN {term!r}: {why}" for term, why in FORBIDDEN.items()
           if term.lower() in low]
    out += [f"FORBIDDEN /{pat}/: {why}" for pat, why in FORBIDDEN_PATTERNS.items()
            if re.search(pat, text)]
    return out
```

Then prove both directions still hold: temporarily add a line containing `the 213/413 target policy` and confirm FAIL, and confirm that the reference entry containing `406–413` alone produces PASS. Paste both outputs into your report. The number gate independently flags a bare `413`, so also add `"413"` and `"406"` to `ALLOWED_NUMBERS` **only** if the reference page range requires it — record in the report which allowlist additions you made and why.

- [ ] **Step 6: Verify every reference is cited and every citation resolves**

```bash
python3 -c "
import sys, re, pathlib; sys.path.insert(0,'paper')
from check import extract_text
t = extract_text(pathlib.Path('paper/out/paper.docx'))
cited = {int(n) for n in re.findall(r'\[(\d+)\]', t)}
listed = t.count('\n')  # replace with the actual reference count after drafting
print('cited numbers:', sorted(cited))
print('max cited:', max(cited) if cited else None)
"
```

Expected: citation numbers form a contiguous run from 1 to the number of reference entries, with no gaps and nothing cited above the list length.

- [ ] **Step 7: Build, check, commit**

```bash
python3 paper/build.py && python3 paper/check.py
git add paper/content.md paper/check.py
git commit -m "docs: draft sections I, II, VI, VII and reference list"
```

---

### Task 7: Fit to six pages and verify format compliance

**Files:**
- Modify: `paper/content.md`

- [ ] **Step 1: Measure the overflow**

Run: `python3 paper/build.py && python3 paper/check.py`
If the page gate fails, record by how much.

- [ ] **Step 2: Cut in the spec's stated order**

Per spec §7, exhibits are cut before prose: first collapse Table I into prose, then Table II. Table III and Figure 1 are mandatory. Within prose, cut in this order: Section II Related Work down to 0.35 p, Section III platform detail, Section IV-B parse-hardening detail. Never cut Section V-C or Section VI.

- [ ] **Step 3: Verify the format rules from spec §9 against the rendered PDF**

```bash
python3 -c "
import fitz
d = fitz.open('paper/out/paper.pdf')
print('pages:', d.page_count)
for i, pg in enumerate(d):
    fonts = {s['font'] for b in pg.get_text('dict')['blocks'] if b['type']==0
             for l in b['lines'] for s in l['spans']}
    sizes = sorted({round(s['size'],1) for b in pg.get_text('dict')['blocks'] if b['type']==0
                    for l in b['lines'] for s in l['spans']})
    print(f'p{i+1} fonts={sorted(fonts)} sizes={sizes}')
"
```

Expected: Times variants only; sizes clustered around 8, 9, 10 and 24 pt. Any other font family means a style was bypassed.

- [ ] **Step 4: Confirm Figure 1 and its caption are not separated across columns**

Task 3 observed that with placeholder content the caption paragraph flowed to the top of column 2 while the image stayed at the bottom of column 1. They are structurally adjacent in document order, so this was LibreOffice breaking the column around short filler text and was expected to resolve once real content landed. Verify it did.

```bash
python3 - <<'PY'
import fitz
d = fitz.open('paper/out/paper.pdf')
for i, pg in enumerate(d):
    blocks = [b for b in pg.get_text('blocks') if 'Fig. 1' in b[4]]
    for b in blocks:
        print(f'caption on page {i+1}: x0={b[0]:.1f} y0={b[1]:.1f}')
    for img in pg.get_image_info():
        print(f'image on page {i+1}: x0={img["bbox"][0]:.1f} y0={img["bbox"][1]:.1f}')
PY
```

Expected: the caption's `x0` matches the image's `x0` (same column) and its `y0` is greater than the image's (immediately below). If they are in different columns, set `keep_with_next` on the image paragraph in `build.py`'s `insert_figure`:

```python
    p.paragraph_format.keep_with_next = True
```

A caption separated from its figure is a real format defect, not a cosmetic one — do not accept it.

- [ ] **Step 5: Confirm the checker passes at six pages or fewer**

Run: `python3 paper/check.py`
Expected: `PASS — 6 pages, all gates clear` (or fewer).

- [ ] **Step 6: Commit**

```bash
git add paper/content.md paper/build.py
git commit -m "docs: fit paper to six-page limit"
```

---

### Task 8: Adversarial review

The checker cannot catch a weak argument or an overreaching claim. Dispatch independent reviewers with distinct briefs, then triage.

**Files:**
- Modify: `paper/content.md` (fixes only)

- [ ] **Step 1: Dispatch three reviewers concurrently, each with a distinct lens**

Give each the built PDF path and the spec path.
1. **Skeptical reviewer** (high-capability model): try to reject the paper. Attack the claim that concordance justifies clearing documents; attack the development-versus-deployed model gap; attack the single-annotator reference standard; attack whether the contribution is novel against INCEpTION-style pre-annotation.
2. **Claims auditor** (mid-capability): check every sentence stating a result against spec §5, and flag any sentence that asserts a behavioural effect on annotators.
3. **Format and mechanics auditor** (small model): typography against spec §9, citation order, caption numbering, template residue, British-versus-American spelling consistency, and figure and table cross-references resolving.

- [ ] **Step 2: Triage the findings**

For each finding decide fix, acknowledge in Section VI, or reject with a reason. A finding that the paper overclaims is always a fix, never a rejection.

- [ ] **Step 3: Apply fixes, rebuild, re-check**

Run: `python3 paper/build.py && python3 paper/check.py`
Expected: PASS, still six pages or fewer.

- [ ] **Step 4: Commit**

```bash
git add paper/content.md
git commit -m "docs: address adversarial review findings"
```

---

### Task 9: Final deliverables

**Files:**
- Create: `paper/out/paper.docx`, `paper/out/paper.pdf` (build artifacts)

- [ ] **Step 1: Resolve the four open items from spec §10 that affect the text**

All four are now resolved and need no further decisions: the title is "An On-Premise LLM Cross-Check Mechanism for Expert Legal Annotation Quality"; §IV-E is written in the present tense with the warning surface described as deployed, subject to the pre-submission liveness check in spec §4 item 6; the batch is reported as 1,294 dated 2026-07-16; and the loader question is settled in spec §8. Confirm each is reflected in the built PDF rather than assuming it.

- [ ] **Step 2: Final clean build**

```bash
rm -rf paper/out && python3 paper/fig1.py && python3 paper/build.py && python3 paper/check.py
```
Expected: PASS.

- [ ] **Step 3: Walk the spec §4 claim-discipline list and the §9 format list against the PDF by hand**

Six checks: no behavioural claim stated as a result; External-100 never called accuracy; the two models never conflated; selection-on-test disclosed; no page numbers; no template text. Confirm each by reading the rendered PDF, not the source.

- [ ] **Step 4: Commit**

```bash
git add paper
git commit -m "docs: final IISEC 2027 paper build"
```

---

## Self-Review

**Spec coverage.** §1 venue constraints → Global Constraints and Task 7. §2 contribution → Task 5 Step 3, Task 6 Step 1. §3 out-of-scope → Task 2 `FORBIDDEN`. §4 claim discipline → Task 2, Task 5 Step 5, Task 8 reviewer 2, Task 9 Step 3. §5 canonical facts → Task 2 `ALLOWED_NUMBERS` and `check_arithmetic`, Task 4 tables. §6 outline → Tasks 5 and 6. §7 exhibits → Tasks 3, 4 and 7 Step 2. §8 references → Task 6 Steps 4 and 5. §9 format → Task 1 Step 5, Task 7 Step 3. §10 open items → Task 9 Step 1.

**Placeholders.** Task 1 deliberately writes placeholder prose; that is the point of a pipeline test and it is replaced in Tasks 5 and 6. Two steps depend on values discovered at execution time rather than assumed here: the template style names in Task 1 Step 1, and the reference count in Task 6 Step 5. Both are discovery steps with a stated expected result, not unfilled gaps.

**Type consistency.** The insertion helper Task 1 delivers is `para_before(doc, anchor, style, text="")` — not `add_paragraph`, which exists only as python-docx's own append-at-end API used inside `para_before` and `insert_figure`. Tasks 3 and 4 consume `para_before` and add `insert_figure(doc, anchor, png_path, caption, width_pt)` and `insert_table(doc, anchor, caption, header, rows)`. `docx_to_pdf(docx_path, outdir)`, `parse_content(path) -> list[tuple[str, str, str]]` and `extract_text(path) -> str` are used consistently across Tasks 1–6. The marker alternation in `parse_content` already declares `FIGURE` and `TABLE` in Task 1, so neither Task 3 nor Task 4 edits that pattern — they add `render()` branches only.

**Known gap.** The style names in `build.py` are written as plausible defaults and are corrected from the Task 1 Step 1 output before Step 5 can pass. This is intentional — assuming them would be the failure mode.
