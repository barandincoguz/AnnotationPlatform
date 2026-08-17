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
