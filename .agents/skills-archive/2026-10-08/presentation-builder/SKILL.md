---
name: presentation-builder
description: >-
  Use this skill whenever asked to generate, create, edit, build, or audit PowerPoint decks,
  PPTX files, presentations, slides, or sunum/slayt documents. Triggers automated PptxGenJS
  generation, slide rendering, MarkItDown text inspection, and quality assurance.
---

# Enterprise Presentation Builder Skill

This skill extends the agent's capability to generate professional, outcome-driven, 16:9 widescreen PowerPoint presentations (`.pptx`) with native PPTX objects, automated PDF/PNG slide rendering, and MarkItDown-powered quality assurance.

## When to Use This Skill

Activate this skill when the user requests:
- Creating or editing a PowerPoint presentation or slide deck.
- Generating a presentation on any technical, business, or research topic.
- Audit, QA, or export of PPTX slides to PDF/PNG images.

## Execution Workflow Steps

1. **Define Objective & Slide Manifest**:
   - Determine target audience and slide count (typically 6-8 slides for a deck).
   - Use outcome-driven titles (e.g. *"Quantifiable ROI: 4.2x Throughput Improvement"*) rather than generic headers (*"Results"*).
   - Prepare structured JSON manifest in `presentation-agent/src/demo_data.json` or custom input path.

2. **Generate Native PPTX**:
   - Run PptxGenJS builder engine:
     ```bash
     cd presentation-agent && npm run build
     ```
   - Verifies native PowerPoint elements (text frames, rounded card shapes, tables, bar charts, speaker notes).

3. **Render PDF, Slide PNGs & Montage Image**:
   - Execute renderer pipeline:
     ```bash
     cd presentation-agent && npm run render
     ```
   - Produces `output/demo.pdf`, `output/demo-1.png` .. `output/demo-8.png`, and stitched `output/demo-montage.png`.

4. **Run Automated Quality Assurance**:
   - Run QA inspection:
     ```bash
     cd presentation-agent && npm run qa
     ```
   - Extracts structured text via `markitdown[pptx]`, checks for unreplaced placeholders (`{{...}}`, `[TODO]`), verifies file integrity, and outputs `output/qa-report.json`.

5. **End-to-End Execution**:
   - Run full pipeline in a single command:
     ```bash
     cd presentation-agent && npm run demo
     ```

## Output Artifacts Checklist

Every completed presentation run must deliver:
- `output/demo.pptx` (Editable PowerPoint presentation)
- `output/demo.pdf` (High-resolution PDF document)
- `output/demo-montage.png` (Visual grid thumbnail montage)
- `output/sources.json` (Sidecar attribution metadata)
- `output/qa-report.json` (QA verification log with 0 critical errors)
