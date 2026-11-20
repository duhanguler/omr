<div align="center">

# OMRKit v2.1

**Zero-calibration Optical Mark Recognition engine with QR auto-template detection, blank-form auto-grid finder, live browser camera scanner, printable ArUco sheet generator, Classical Test Theory psychometrics, FastAPI REST API, and React Web Studio.**

[![License: MIT](https://img.shields.io/badge/License-MIT-0F8A5F.svg?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-14181F.svg?style=flat-square)](pyproject.toml)
[![FastAPI + React Studio](https://img.shields.io/badge/Studio-FastAPI_%2B_React_19-1D4ED8.svg?style=flat-square)](#web-studio--rest-api)
[![Code style: ruff](https://img.shields.io/badge/Lint-Ruff_%2B_Mypy-525B68.svg?style=flat-square)](pyproject.toml)

[English](README.md) · [Türkçe](README.tr.md) · [Examples](examples/) · [Contributing](CONTRIBUTING.md)

</div>

---

## Why OMRKit?

Traditional open-source OMR scripts force you to hand-edit pixel coordinates in brittle JSON files, break on rotated mobile photos, fail on checkmarks/crosses, and dump raw CSVs without confidence scores or grading analytics. **OMRKit v2.1** solves the entire lifecycle in one clean MIT-licensed toolkit:

| Capability | Legacy OMR Scripts | **OMRKit v2.1** |
| :--- | :---: | :---: |
| **Printable PDF Sheet Generator + Auto Template** | Manual JSON pixels | **1-Click Vector PDF (ArUco + QR) + Exact `template.json`** |
| **Zero-Template QR Auto-Scanning** | Must pass template manually | **`omrkit scan sheet.jpg` auto-detects template from QR** |
| **Auto-Detect Grids on Existing Blank Forms** | Measure pixels by hand | **`omrkit detect-layout blank.jpg` + Studio Canvas Wizard** |
| **Live Webcam / Mobile Browser Scanner** | Static files only | **Real-time `getUserMedia` Viewfinder with Auto-Lock** |
| **Multi-Page PDF & EXIF Auto-Orientation** | Single images only | **Native `pypdfium2` + EXIF Auto-Orient** |
| **0° / 90° / 180° / 270° Auto-Rotation** | Breaks when sideways | **ArUco IDs + Template-Structure Disambiguation** |
| **Checkmarks (✓), Crosses (✗) & Shadow Tolerance** | Global intensity only | **Illumination Normalization + Hybrid Ink Scorer** |
| **Confidence Scores & Human-in-the-Loop (HITL)** | Silent errors in CSV | **Calibrated `0–1` Confidence + 1-Click Review Queue** |
| **Exam Psychometrics & Scorecards** | Basic score sum | **CTT Difficulty ($p$), Discrimination ($D$), KR-20, Excel & PDF Cards** |
| **Legacy `OMRChecker` Template Migration** | Manual rewrite | **`omrkit migrate-template old.json -o new.json`** |

---

## Real-World Detection & Generated Sheets

<table>
  <tr>
    <td width="54%" align="center">
      <img src="docs/assets/scan_overlay_demo.jpg" alt="OMRKit real-world phone scan verification overlay" />
      <br />
      <sub><b>Real mobile photo scan:</b> Emerald = confident (including ✓ & ✗ marks), Crimson = multi-marked, Amber = faint marks queued for 1-click HITL review.</sub>
    </td>
    <td width="46%" align="center">
      <img src="docs/assets/generated_sheet_preview.jpg" alt="OMRKit generated ArUco + QR optical answer sheet" />
      <br />
      <sub><b>Zero-calibration generated PDF:</b> Vector A4/Letter layout with ArUco corners [0,1,2,3], embedded auto-detect QR badge, and exact companion <code>template.json</code>.</sub>
    </td>
  </tr>
</table>

---

## Quickstart (60 Seconds)

### 1. Install

```bash
git clone https://github.com/duhanguler/omr.git
cd omr
pip install -e ".[all]"
```

*(Or run via Docker with zero local setup: `docker compose up` → open `http://localhost:8000` and click **Try Demo**!)*

### 2. Generate a Print-Ready ArUco + QR Sheet

```bash
omrkit generate --preset standard_mcq_40 -o my_exam
# Writes: standard_mcq_40_sheet.pdf, template.json, answer_key.json
```

Built-in presets (`omrkit generate --list`):
- `quick_quiz_20` — 20 questions (A–D), 6-digit Student ID
- `standard_mcq_40` — 40 questions (A–E), 8-digit Student ID, Booklet (A–D)
- `turkish_exam_50` — 50 questions (A–E), 6-digit Sınav Kodu, 11-digit **TC Kimlik No** (with checksum validation), Booklet
- `turkish_yks_120` — 120-question YKS / TYT layout (4 columns × 30 rows)

### 3. Scan Images or Multi-Page PDFs (Explicit or Zero-Template QR Auto-Scan)

```bash
# Zero-template QR auto-detection on generated sheets:
omrkit scan examples/standard_mcq_40q/scans -o outputs/auto_demo

# Explicit template + YKS/TYT negative marking + Excel & PDF scorecards:
omrkit scan examples/standard_mcq_40q/scans \
  -t examples/standard_mcq_40q/template.json \
  -k examples/standard_mcq_40q/answer_key.json \
  --policy yks_tyt \
  --format csv,json,xlsx,scorecards \
  -o outputs/demo

# Auto-detect bubble grids from ANY existing blank optical sheet:
omrkit detect-layout examples/turkish_exam_50q/blank_form.jpg -o auto_template.json

# Migrate a legacy OMRChecker v1 template.json in one command:
omrkit migrate-template old_template.json -o template_v2.json
```

Try the real-world hand-marked Turkish 50-question mobile scans too:

```bash
omrkit scan examples/turkish_exam_50q/scans \
  -t examples/turkish_exam_50q/template.json \
  -o outputs/turkish_demo
```

### 4. Launch Visual Web Studio & REST API

```bash
omrkit studio
# Web Studio:    http://127.0.0.1:8000
# OpenAPI Docs:  http://127.0.0.1:8000/docs
```

---

## Python SDK

Integrate optical scanning, grading, and psychometrics in 10 lines of typed Python:

```python
from omrkit import AnswerKey, ExamGrader, GradingPolicy, OMRScanner, Template

template = Template.from_file("examples/standard_mcq_40q/template.json")
scanner = OMRScanner(template)

batch = scanner.scan_batch("examples/standard_mcq_40q/scans", workers=4)

key = AnswerKey.from_file("examples/standard_mcq_40q/answer_key.json")
report = ExamGrader(key, GradingPolicy.preset("yks_tyt")).grade_batch(batch.sheets)

print(f"Graded {report.analytics.student_count} sheets | Mean: {report.analytics.mean_score}")
print(f"KR-20 Reliability: {report.analytics.kr20_reliability}")
```

---

## Architecture

```mermaid
flowchart LR
    A["Images / Multi-Page PDF"] --> B["EXIF Auto-Orient + PDFium Loader"]
    B --> C["5-Mode Registration: ArUco / Markers / PageQuad / ORB / Direct"]
    C --> D["Shadow & Illumination Normalization"]
    D --> E["Hybrid Bubble Detector (Fill + Ring Contrast + Ink Stroke)"]
    E --> F{"Confidence & Validator Check"}
    F -- "High Confidence" --> G["ExamGrader + CTT Psychometrics"]
    F -- "Low Conf / Multi-Mark / Bad Checksum" --> H["HITL Review Queue (Web Studio)"]
    H --> G
    G --> I["CSV / JSON / Multi-Sheet Excel / PDF Scorecards / Overlays"]
```

### Key Technical Features
- **5 Registration Engines:** `aruco` (instant 0/90/180/270° recovery), `markers` (multi-scale concentric markers with template-structure orientation recovery), `page_quad` (borderless page contour), `homography` (ORB + RANSAC), and `none` (flatbed).
- **Shape-Aware Hybrid Bubble Classifier:** Evaluates inner circular fill ratio, 75th-percentile local ring contrast (immune to printed borders/numbers), and dark ink stroke density so pen checkmarks (`✓`) and crosses (`✗`) read accurately while smudges and multi-marks route to the HITL review queue.
- **Built-in Field Validators:** Algorithmic **Turkish TC Kimlik No** (11-digit mod-10/11), **Luhn**, `digits`, and `non_empty` validators flag misread IDs automatically.
- **Classical Test Theory (CTT) Psychometrics:** Mean, median, standard deviation, percentiles, per-item difficulty ($p$), upper/lower 27% discrimination index ($D$), option distractor distribution, and **KR-20** internal consistency reliability.
- **Grading Policies:** Standard, Turkish **YKS/TYT & KPSS** (4 wrong = -1 correct), **LGS** (3 wrong = -1 correct), multi-booklet (`A/B/C/D`), bonus/cancelled questions, and weighted sections.
- **Privacy Utility:** `omrkit strip-exif <dir> -o <clean_dir>` permanently bakes EXIF orientation into pixels and removes GPS/device metadata.

---

## Reproducible Benchmarks

Run `omrkit benchmark --samples 5` on your own machine to reproduce:

| Scenario (`standard_mcq_40`, 245 fields/scenario) | Accuracy | Avg Confidence | False HITL Flags | Single-Thread Throughput |
| :--- | :---: | :---: | :---: | :---: |
| Clean Flatbed Scan (Solid Fill) | **100.00%** | 99.2% | 0 | **~530 OMR/min** |
| Mobile Perspective + Uneven Shadow | **100.00%** | 99.2% | 0 | **~310 OMR/min** |
| Rotated 90° / 180° / 270° + Perspective | **100.00%** | 99.2% | 0 | **~415 OMR/min** |
| Pen Checkmarks (`✓`) + Shadow | **100.00%** | 99.1% | 0 | **~440 OMR/min** |

*(Multi-process batch mode via `--workers N` scales linearly across CPU cores.)*

---

## Web Studio & REST API

OMRKit Studio ships pre-bundled inside the Python package and launches via `omrkit studio` or `docker compose up` (includes a **Try Demo** button in the header for instant 1-click exploration):

1. **Scan & Review (HITL):** Drag-and-drop JPG/PNG/PDF batches with explicit template or **QR Auto-Detect**, inspect zoomable color-coded verification overlays, resolve flagged bubbles with 1-click overrides, and export CSV/Excel.
2. **Live Camera:** Real-time browser webcam / smartphone camera viewfinder (`getUserMedia`) with **Auto-Lock** corner capture, audio confirmation, and QR template recognition.
3. **Template Designer:** Upload any blank optical form image or PDF, click **Auto-Detect Grids** to find circular bubble blocks automatically, import legacy `OMRChecker` templates (**Migrate v1**), or draw blocks directly on the HTML5 canvas.
4. **Sheet Generator:** Customize title, question count (5–120), option labels, booklet selector, and ID grids; preview live and download a ready-to-print ZIP bundle (`PDF + template.json + answer_key.json`).
5. **Grading & Analytics:** Inline answer-key editor, scoring policy selector, score histogram, student scoreboard with per-student **PDF Scorecards**, and full CTT item psychometrics.

### REST API Endpoints
- `GET /api/health` · `GET /api/presets`
- `POST /api/generate` · `POST /api/generate/bundle`
- `POST /api/templates/validate` · `POST /api/templates/auto-detect` · `POST /api/templates/migrate` · `POST /api/preview-image`
- `POST /api/scan` *(supports `template_json="auto"`)* · `POST /api/demo/cohort` · `POST /api/grade`
- `POST /api/export/csv` · `POST /api/export/xlsx` · `POST /api/export/scorecard`

---

## Development

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[all,dev]"

# Python QA
.venv/bin/ruff check src tests
.venv/bin/mypy src/omrkit
.venv/bin/pytest -v --cov=omrkit

# Frontend Studio development
cd studio && npm ci && npm run dev
```

---

## License

Released under the [MIT License](LICENSE). Copyright © 2026 Duhan Güler & Contributors.
