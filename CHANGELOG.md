# Changelog

All notable changes to **OMRKit** are documented in this file.

## [2.1.1] - 2026-11-20

### Security
- **Blocked Local Filesystem Probing via HTTP API (`POST /api/scan`):** Disallowed `registration.marker_path` and `registration.reference_path` over the HTTP API (`HTTP 400`), preventing server file-existence oracle and local image file reads while preserving local CLI/Python SDK support.
- **Prevented Remote OOM DoS Vectors:** Bounded API `dpi` (`72..350`), enforced a `40M` pixel budget and 0-page check in `omrkit.io.loader`, capped single label range expansions (`<= 2000`), total template fields (`<= 5000`), and page dimensions (`<= 12000px`).
- **Sanitized `Content-Disposition` Filenames:** Transliterated Turkish/Unicode characters and stripped unsafe header characters in `/api/export/scorecard` and `/api/generate/bundle`, eliminating both header injection and HTTP 500 crashes on Turkish `sheet_id`s.

### Fixed
- **CV & Registration:** Replaced sum/diff heuristic in `order_quad_points` with centroid polar-angle ordering so 45°-tilted quads always yield 4 distinct corners; guarded `grid_finder` against tiny noisy Y-gaps and >26 option labels; fixed exact option token matching in `visualizer.py` and `benchmark.py`.
- **Core, Grading & Validators:** Required ASCII digits in `validate_tr_tckn`, `validate_luhn`, and `validate_digits` (fixing `ValueError` crashes on Unicode superscript digits like `²`); emitted HITL `ReviewItem`s for ungrouped field validator failures; ensured unique `sheet_id` disambiguation across batches/uploads; fixed `partial_credit` gaming and exact multi-answer full credit; hardened `SheetSpec` column/width validation; supported digit-containing label prefixes (`sec1_q1..20`); hardened `migrator.py` validation and `customLabels` range matching; paginated 160+ question PDF scorecards; fixed `omrkit grade` JSON list input and `omrkit generate --questions` column auto-adjustment.
- **REST API & Performance:** Cached `GET /api/presets` via `@lru_cache`; mapped invalid `/api/demo/cohort` presets (`400`) and invalid `/api/grade` policy ranges (`422`) instead of HTTP 500; synthesized valid TC Kimlik No checksums in `turkish_exam_50` demo cohorts; unified version strings via `omrkit._version.__version__`.
- **Web Studio:** Fixed `TemplateDesigner` comma-separated options/labels input editing, browser freeze cap on range previews, and stuck canvas drag rectangles; debounced `SheetGenerator` PDF previews (`300ms` + `AbortController`) with column auto-clamping; fixed `CameraScanner` `AudioContext` leaks, sub-second duplicate capture IDs, and unmount races; fixed `App.tsx` HITL overrides to recompute confidence, update bubble flags, and invalidate stale grades; added multi-booklet Answer Key editor and policy sync in `AnalyticsView`; added visible error handling on **Try Demo** and file input resets across views.

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
