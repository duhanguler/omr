# Changelog

All notable changes to **OMRKit** are documented in this file.

## [2.1.0] - 2026-11-20

### Added
- **QR Code Auto-Template Discovery (`omrkit.vision.qr`, `omrkit.core.auto_scanner`):** Every generated PDF embeds an OpenCV-native QR template badge enabling zero-template scanning via `omrkit scan <input>` (omitting `-t`), `scan_image_auto()`, and `POST /api/scan` (`template_json="auto"`).
- **Automatic Blank-Form Bubble Grid Finder (`omrkit.vision.grid_finder`):** Detects circular bubbles on arbitrary blank optical sheets and clusters them into ready-to-use `FieldBlock` definitions via `omrkit detect-layout`, `POST /api/templates/auto-detect`, and the Studio **Auto-Detect Grids** button.
- **Live Browser Camera / Webcam Scanner (`studio/src/views/CameraScanner.tsx`):** Real-time `getUserMedia` viewfinder with corner guide reticle, Auto-Lock sheet capture, audio confirmation, and QR auto-recognition.
- **One-Click Interactive Demo Mode (`POST /api/demo/cohort`):** Header **Try Demo** button in Web Studio loads a realistic 5-student cohort (clean, shadow/warp, 90°-rotated checkmarks, multi-marked HITL review item) with full YKS/TYT grading and CTT psychometrics.
- **Legacy `OMRChecker` v1 Template Migrator (`omrkit.core.migrator`):** One-command conversion via `omrkit migrate-template`, `POST /api/templates/migrate`, and Studio **Migrate v1**.
- **Cloud Deploy Support:** Automatic `$PORT` handling in `omrkit studio` and `Dockerfile`.

### Fixed
- Resolved NumPy 2.x / Python 3.12 strict `mypy` overload checks in `omrkit.vision.registration`.

## [2.0.0] - 2026-11-20

### Added
- **Clean-room MIT-licensed Python package (`omrkit`)** with strict typing (`mypy`) and Pydantic v2 schemas.
- **Unified Document Loader (`omrkit.io.loader`)**: EXIF auto-orientation for mobile images and native multi-page PDF rasterization via `pypdfium2`.
- **5-Mode Registration Engine (`omrkit.vision.registration`)**: ArUco (`DICT_4X4_50` with automatic 0°/90°/180°/270° orientation), multi-scale custom/concentric markers with template-structure auto-rotation, page quadrilateral, ORB+RANSAC homography, and flatbed identity mode.
- **Hybrid Shape-Aware Bubble Detector (`omrkit.vision.detector`)**: Illumination/shadow normalization, inner-core fill ratio, 75th-percentile local ring contrast, ink stroke scoring (supporting ✓ and ✗ marks), calibrated `0–1` confidence, and HITL review flags.
- **Printable PDF Sheet Generator (`omrkit.generator`)**: Vector ReportLab A4/Letter PDF generator with ArUco corners and mathematically exact companion `template.json` + presets (`quick_quiz_20`, `standard_mcq_40`, `turkish_exam_50`, `turkish_yks_120`).
- **Exam Grader & Classical Test Theory Psychometrics (`omrkit.grading`)**: Multi-booklet mapping, negative marking presets (`yks_tyt`, `kpss`, `lgs`, `standard`), Turkish TC Kimlik No & Luhn validators, item difficulty ($p$), discrimination ($D$), distractor frequencies, and KR-20 reliability.
- **Multi-Format Exporters (`omrkit.io.exporters`)**: CSV, JSON, formatted multi-sheet Excel (`.xlsx`), annotated verification overlays, and printable A4 PDF student scorecards.
- **Typer + Rich CLI (`omrkit`)**: `scan`, `generate`, `grade`, `validate`, `benchmark`, `strip-exif`, and `studio`.
- **FastAPI REST API & React 19 + Vite + Tailwind Web Studio**: Scan & HITL Review workspace, interactive HTML5 Canvas Visual Template Designer, live Sheet Generator, and Grading & Psychometrics dashboard.
- **DevOps & Examples**: Multi-stage `Dockerfile`, `docker-compose.yml`, GitHub Actions CI & Release workflows, EXIF-cleaned real-world Turkish 50Q scans, and ArUco sample datasets.
