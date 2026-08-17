"""Generate Figure 1 (architecture) as a 300 dpi PNG sized for one IEEE column."""
from pathlib import Path

import fitz
from reportlab.lib.colors import black, white
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "out"
W, H = 252, 210  # points; 252 pt is one IEEE column


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

    def arrow(x1, y1, x2, y2):
        c.line(x1, y1, x2, y2)
        c.line(x2, y2, x2 - 3, y2 + 4)
        c.line(x2, y2, x2 + 3, y2 + 4)

    # Row A: the two independent extraction sources.
    box(6, 164, 110, 34, ["Annotation platform", "(human annotator)"])
    box(136, 164, 110, 34, ["Background LLM", "worker (local)"])

    # Row B: the comparison stage.
    box(6, 112, 240, 30, ["Comparison: legal-key alignment", "+ verbatim-quote grounding"])

    # Row C: the four outcome buckets. Widths are sized to each label at 8 pt Times
    # (QUARANTINE needs far more room than RED), not split evenly.
    box(6, 64, 44, 26, ["GREEN"])
    box(58, 64, 52, 26, ["YELLOW"])
    box(118, 64, 36, 26, ["RED"])
    box(162, 64, 84, 26, ["QUARANTINE"])

    # Row D: the two downstream outcomes.
    box(6, 12, 110, 30, ["Cleared", "(no review)"])
    box(136, 12, 110, 30, ["Expert review", "+ annotator warning"])

    # A -> B: each source feeds the comparison stage.
    arrow(61, 164, 61, 142)
    arrow(191, 164, 191, 142)

    # B -> C: the comparison fans out into all four buckets (drawn explicitly,
    # one line per bucket, rather than one line that would visually land on
    # only one of them).
    bucket_centers = [28, 84, 136, 204]  # GREEN, YELLOW, RED, QUARANTINE
    for bx in bucket_centers:
        arrow(126, 112, bx, 90)

    # C -> D: GREEN clears without review; YELLOW, RED and QUARANTINE all
    # route to expert review (only GREEN reaches the "no review" outcome).
    arrow(28, 64, 61, 42)
    arrow(84, 64, 191, 42)
    arrow(136, 64, 191, 42)
    arrow(204, 64, 191, 42)

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
