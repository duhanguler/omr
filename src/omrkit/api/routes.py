"""FastAPI REST API routes powering OMRKit Web Studio and third-party integrations."""

from __future__ import annotations

import base64
import io
import json
import random
import re
import zipfile
from functools import lru_cache
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from omrkit._version import __version__
from omrkit.api.settings import APISettings, get_api_settings
from omrkit.core.auto_scanner import scan_bytes_auto
from omrkit.core.benchmark import apply_camera_distortion, render_synthetic_filled_sheet
from omrkit.core.migrator import migrate_legacy_template_dict
from omrkit.core.scanner import OMRScanner
from omrkit.generator.pdf_sheet import SheetGenerator
from omrkit.generator.presets import SheetSpec, get_sheet_preset, get_sheet_presets
from omrkit.grading.grader import ExamGrader
from omrkit.io.exporters import (
    export_csv_string,
    export_excel_bytes,
    export_pdf_scorecard_bytes,
)
from omrkit.io.loader import DocumentLoadError, load_bytes
from omrkit.models.grading import AnswerKey, GradingPolicy, GradingReport, StudentGrade
from omrkit.models.scan import SheetResult
from omrkit.models.template import Template
from omrkit.vision.grid_finder import detect_layout_from_blank
from omrkit.vision.visualizer import render_annotated_sheet

router = APIRouter(prefix="/api", tags=["omrkit"])

_TURKISH_ASCII_MAP = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_download_filename(raw_stem: str, suffix: str) -> str:
    """Produce an ASCII-safe, header-injection-proof download filename."""
    cleaned = raw_stem.translate(_TURKISH_ASCII_MAP)
    cleaned = _SAFE_FILENAME_RE.sub("_", cleaned).strip("._-")
    if not cleaned:
        cleaned = "omrkit"
    return f"{cleaned[:80]}{suffix}"


def _make_valid_demo_tckn(seed_index: int) -> str:
    """Synthesize a checksum-valid 11-digit Turkish TC Kimlik No for demo cohorts."""
    base = 100000001 + seed_index * 13729
    digits = [int(ch) for ch in str(base)[:9]]
    odd_sum = sum(digits[0:9:2])
    even_sum = sum(digits[1:8:2])
    d10 = ((odd_sum * 7) - even_sum) % 10
    d11 = (sum(digits) + d10) % 10
    return "".join(str(d) for d in (*digits, d10, d11))


async def _read_bounded_upload(upload: UploadFile, settings: APISettings) -> bytes:
    """Read an uploaded file enforcing the configured byte limit cleanly."""
    limit = settings.max_upload_bytes
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File '{upload.filename or 'upload'}' exceeds maximum allowed upload size "
                f"of {settings.max_upload_mb} MB."
            ),
        )
    return data


def _encode_image_data_url(image_bgr: np.ndarray, fmt: str = ".jpg", quality: int = 86) -> str:
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if fmt == ".jpg" else []
    ok, encoded = cv2.imencode(fmt, image_bgr, params)
    if not ok:
        raise RuntimeError("Failed to encode image buffer.")
    mime = "image/jpeg" if fmt == ".jpg" else "image/png"
    b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _encode_overlay(warped_bgr: np.ndarray, result: SheetResult) -> str:
    annotated = render_annotated_sheet(warped_bgr, result)
    h, w = annotated.shape[:2]
    if max(h, w) > 1500:
        scale = 1500.0 / float(max(h, w))
        annotated = cv2.resize(
            annotated,
            (round(w * scale), round(h * scale)),
            interpolation=cv2.INTER_AREA,
        )
    return _encode_image_data_url(annotated, fmt=".jpg", quality=85)


def _extract_review_crops(warped_bgr: np.ndarray, result: SheetResult) -> dict[str, str]:
    """Extract crisp zoomed JPEG bubble-strip crops for every HITL review item."""
    if not result.review_items:
        return {}
    h, w = warped_bgr.shape[:2]
    crops: dict[str, str] = {}
    for item in result.review_items:
        x1, y1, x2, y2 = item.bbox
        cx1 = max(0, x1 - 10)
        cy1 = max(0, y1 - 8)
        cx2 = min(w, x2 + 10)
        cy2 = min(h, y2 + 8)
        if cx2 - cx1 < 12 or cy2 - cy1 < 12:
            continue
        patch = warped_bgr[cy1:cy2, cx1:cx2]
        ph, pw = patch.shape[:2]
        if max(ph, pw) > 480:
            scale = 480.0 / float(max(ph, pw))
            patch = cv2.resize(
                patch,
                (max(16, round(pw * scale)), max(16, round(ph * scale))),
                interpolation=cv2.INTER_AREA,
            )
        crops[item.field_id] = _encode_image_data_url(patch, fmt=".jpg", quality=88)
    return crops


class GradeRequest(BaseModel):
    """Request body for grading scanned sheets with an answer key and policy."""

    sheets: list[SheetResult]
    answer_key: AnswerKey
    policy: GradingPolicy = Field(default_factory=GradingPolicy)


class ExportRequest(BaseModel):
    """Request body for exporting scan and optional grading results."""

    sheets: list[SheetResult]
    report: GradingReport | None = None


class ScorecardRequest(BaseModel):
    """Request body for rendering a single student's PDF scorecard."""

    grade: StudentGrade
    exam_name: str = "Exam Scorecard"


class MigrateTemplateRequest(BaseModel):
    """Request body for migrating a legacy OMRChecker v1 template."""

    name: str = "migrated_template"
    legacy_template: dict[str, Any]


@router.get("/health")
def health_check() -> dict[str, Any]:
    """Return service health, package version, demo mode flag, and upload guardrails."""
    settings = get_api_settings()
    return {
        "status": "ok",
        "service": "omrkit",
        "version": __version__,
        "demo_mode": settings.demo_mode,
        "limits": settings.limits_dict(),
    }


@lru_cache(maxsize=1)
def _cached_presets_payload() -> dict[str, Any]:
    generator = SheetGenerator()
    sheet_presets: list[dict[str, Any]] = []
    for preset_id, spec in get_sheet_presets().items():
        generated = generator.generate(spec)
        sheet_presets.append(
            {
                "id": preset_id,
                "spec": spec.model_dump(mode="json"),
                "template": generated.template.model_dump(mode="json"),
                "sample_answer_key": generated.sample_answer_key.model_dump(mode="json"),
            }
        )

    policy_names = ["standard", "yks_tyt", "kpss", "lgs", "sat_legacy"]
    grading_policies = [GradingPolicy.preset(name).model_dump(mode="json") for name in policy_names]

    return {
        "sheet_presets": sheet_presets,
        "grading_policies": grading_policies,
    }


@router.get("/presets")
def list_presets() -> dict[str, Any]:
    """Return built-in optical sheet presets (with exact templates) and grading policies."""
    return _cached_presets_payload()


@router.post("/generate")
def generate_sheet(spec: SheetSpec) -> dict[str, Any]:
    """Generate a printable PDF (base64), matching exact Template, and sample AnswerKey."""
    try:
        generated = SheetGenerator().generate(spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    pdf_b64 = base64.b64encode(generated.pdf_bytes).decode("ascii")
    preview_page = load_bytes(generated.pdf_bytes, f"{spec.preset_id}.pdf", dpi=140)[0]
    return {
        "filename": _safe_download_filename(spec.preset_id, "_sheet.pdf"),
        "pdf_base64": pdf_b64,
        "preview_data_url": _encode_image_data_url(preview_page.image_bgr, fmt=".jpg", quality=88),
        "template": generated.template.model_dump(mode="json"),
        "sample_answer_key": generated.sample_answer_key.model_dump(mode="json"),
    }


@router.post("/generate/bundle")
def generate_sheet_bundle(spec: SheetSpec) -> Response:
    """Download a ZIP archive containing the PDF sheet, template.json, and answer_key.json."""
    try:
        generated = SheetGenerator().generate(spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    pdf_name = _safe_download_filename(spec.preset_id, "_sheet.pdf")
    zip_name = _safe_download_filename(spec.preset_id, "_bundle.zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(pdf_name, generated.pdf_bytes)
        zf.writestr(
            "template.json",
            json.dumps(generated.template.model_dump(mode="json"), indent=2),
        )
        zf.writestr(
            "answer_key.json",
            json.dumps(generated.sample_answer_key.model_dump(mode="json"), indent=2),
        )
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


@router.post("/templates/validate")
def validate_template(template: Template) -> dict[str, Any]:
    """Validate a Template payload and return expanded bubble coordinates for canvas preview."""
    preview_bubbles: list[dict[str, Any]] = []
    for block in template.blocks:
        for field_id, coords in block.iter_field_bubbles():
            for c in coords:
                preview_bubbles.append(
                    {
                        "block": block.name,
                        "field_id": field_id,
                        "option": c.option,
                        "cx": c.cx,
                        "cy": c.cy,
                        "radius": c.radius,
                    }
                )
    return {
        "valid": True,
        "name": template.name,
        "blocks_count": len(template.blocks),
        "fields_count": len(template.all_field_ids()),
        "grouped_columns": template.grouped_field_names(),
        "preview_bubbles": preview_bubbles,
    }


@router.post("/templates/auto-detect")
async def auto_detect_template_layout(
    file: UploadFile = File(...),
    dpi: int = Form(200, ge=72, le=350),
) -> dict[str, Any]:
    """Automatically detect circular bubble grids on an uploaded blank sheet image/PDF."""
    settings = get_api_settings()
    data = await _read_bounded_upload(file, settings)
    fname = file.filename or "blank_sheet.png"
    try:
        pages = load_bytes(data, filename=fname, dpi=dpi, max_pages=settings.max_pdf_pages)
        if not pages:
            raise DocumentLoadError(f"Document '{fname}' contains 0 pages.")
        page = pages[0]
        template, bubbles_count = detect_layout_from_blank(
            page.image_bgr, template_name=fname.rsplit(".", 1)[0]
        )
    except (DocumentLoadError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "template": template.model_dump(mode="json"),
        "detected_bubbles": bubbles_count,
        "blocks_count": len(template.blocks),
        "fields_count": len(template.all_field_ids()),
        "image_data_url": _encode_image_data_url(page.image_bgr, fmt=".jpg", quality=88),
    }


@router.post("/templates/migrate")
def migrate_legacy_template_endpoint(payload: MigrateTemplateRequest) -> dict[str, Any]:
    """Convert a legacy OMRChecker v1 template JSON to OMRKit v2.0 format."""
    try:
        template = migrate_legacy_template_dict(payload.legacy_template, name=payload.name)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Migration failed: {exc}") from exc
    return {"template": template.model_dump(mode="json")}


@router.post("/preview-image")
async def preview_uploaded_document(
    file: UploadFile = File(...),
    dpi: int = Form(200, ge=72, le=350),
) -> dict[str, Any]:
    """Decode any uploaded image or PDF first page for the Visual Template Designer canvas."""
    settings = get_api_settings()
    data = await _read_bounded_upload(file, settings)
    try:
        pages = load_bytes(
            data,
            filename=file.filename or "upload.png",
            dpi=dpi,
            max_pages=settings.max_pdf_pages,
        )
        if not pages:
            raise DocumentLoadError("Uploaded document contains 0 pages.")
    except DocumentLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    page = pages[0]
    return {
        "filename": page.source_name,
        "page_count": len(pages),
        "width": page.original_width,
        "height": page.original_height,
        "image_data_url": _encode_image_data_url(page.image_bgr, fmt=".jpg", quality=90),
    }


@router.post("/scan")
async def scan_uploaded_sheets(
    files: list[UploadFile] = File(...),
    template_json: str = Form("auto"),
    include_overlay: bool = Form(True),
    dpi: int = Form(200, ge=72, le=350),
) -> dict[str, Any]:
    """Scan uploaded images/PDFs against a template JSON or 'auto' (QR auto-detection)."""
    settings = get_api_settings()
    if len(files) > settings.max_files_per_scan:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Too many files ({len(files)}); maximum allowed per request is "
                f"{settings.max_files_per_scan}."
            ),
        )

    auto_mode = template_json.strip().lower() in {"", "auto"}
    scanner: OMRScanner | None = None
    template_name = "auto"

    if not auto_mode:
        try:
            template = Template.model_validate(json.loads(template_json))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid template JSON: {exc}") from exc

        # Security guardrail: disallow probing or reading local server paths via HTTP API
        if template.registration.marker_path or template.registration.reference_path:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Local server filesystem paths ('marker_path' / 'reference_path') are "
                    "disabled on the HTTP API for security. Use 'aruco', 'page_quad', or 'none' "
                    "over HTTP, or run local marker/homography templates via the CLI/Python SDK."
                ),
            )
        scanner = OMRScanner(template=template, dpi=dpi)
        template_name = template.name

    sheets: list[dict[str, Any]] = []
    overlays: dict[str, str] = {}
    review_crops: dict[str, dict[str, str]] = {}
    sheet_dimensions: dict[str, tuple[int, int]] = {}
    seen_ids: dict[str, int] = {}
    total_elapsed = 0.0
    flagged_count = 0
    failed_count = 0

    def _next_unique_id(base_id: str) -> str:
        count = seen_ids.get(base_id, 0)
        if count == 0:
            seen_ids[base_id] = 1
            return base_id
        candidate = f"{base_id}_{count + 1}"
        while candidate in seen_ids:
            count += 1
            candidate = f"{base_id}_{count + 1}"
        seen_ids[base_id] = count + 1
        seen_ids[candidate] = 1
        return candidate

    for upload in files:
        raw_bytes = await _read_bounded_upload(upload, settings)
        fname = upload.filename or "sheet.png"
        try:
            page_results = (
                scan_bytes_auto(
                    raw_bytes,
                    filename=fname,
                    dpi=dpi,
                    max_pages=settings.max_pdf_pages,
                )
                if scanner is None
                else scanner.scan_bytes(
                    raw_bytes,
                    filename=fname,
                    max_pages=settings.max_pdf_pages,
                )
            )
        except DocumentLoadError as exc:
            if "exceeding the configured limit" in str(exc):
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            failed_count += 1
            unique_err_id = _next_unique_id(fname)
            sheets.append(
                SheetResult(
                    sheet_id=unique_err_id,
                    source_file=fname,
                    template_name=template_name,
                    overall_confidence=0.0,
                    registration_method="auto" if auto_mode else "unknown",
                    registration_score=0.0,
                    error=str(exc),
                ).model_dump(mode="json")
            )
            continue

        for result, warped_bgr in page_results:
            result.sheet_id = _next_unique_id(result.sheet_id)
            total_elapsed += result.elapsed_ms
            if result.error is not None:
                failed_count += 1
            elif result.review_items:
                flagged_count += 1
            sheets.append(result.model_dump(mode="json"))

            if warped_bgr is not None:
                wh, ww = warped_bgr.shape[:2]
                sheet_dimensions[result.sheet_id] = (ww, wh)
                if include_overlay:
                    overlays[result.sheet_id] = _encode_overlay(warped_bgr, result)
                crops = _extract_review_crops(warped_bgr, result)
                if crops:
                    review_crops[result.sheet_id] = crops

    return {
        "template_name": template_name,
        "total_sheets": len(sheets),
        "flagged_sheets": flagged_count,
        "failed_sheets": failed_count,
        "total_elapsed_ms": round(total_elapsed, 2),
        "sheets": sheets,
        "overlays": overlays,
        "review_crops": review_crops,
        "sheet_dimensions": sheet_dimensions,
    }


@router.post("/demo/cohort")
def run_one_click_demo_cohort(preset_id: str = "quick_quiz_20") -> dict[str, Any]:
    """Synthesize, scan, and grade a realistic 5-student exam cohort for 1-click live demos."""
    try:
        spec = get_sheet_preset(preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    generated = SheetGenerator().generate(spec)
    template = generated.template
    answer_key = generated.sample_answer_key
    blank = load_bytes(generated.pdf_bytes, f"{preset_id}.pdf", dpi=spec.dpi)[0].image_bgr
    scanner = OMRScanner(template)

    expected_map = answer_key.resolve_booklet(answer_key.default_booklet)
    profiles = [
        ("student_01_top_scorer", 0.95, 0, 0.0, 0.0, "solid", False),
        ("student_02_mobile_shadow", 0.80, 0, 0.045, 0.30, "solid", False),
        ("student_03_rotated_checkmarks", 0.70, 90, 0.03, 0.18, "checkmark", False),
        ("student_04_hitl_multimark", 0.65, 0, 0.02, 0.12, "solid", True),
        ("student_05_struggling", 0.35, 180, 0.035, 0.20, "solid", False),
    ]

    scanned_sheets: list[SheetResult] = []
    overlays: dict[str, str] = {}
    review_crops: dict[str, dict[str, str]] = {}
    sheet_dimensions: dict[str, tuple[int, int]] = {}
    total_elapsed = 0.0

    for idx, (sid, skill, rot, persp, shadow, style, inject_hitl) in enumerate(profiles):
        rng = random.Random(700 + idx)
        answers: dict[str, str] = {}
        valid_tckn = _make_valid_demo_tckn(idx)
        for block in template.blocks:
            labels = block.expanded_labels()
            if block.validator == "tr_tckn" and len(labels) == 11:
                for f_idx, fid in enumerate(labels):
                    answers[fid] = valid_tckn[f_idx]
                continue
            for f_idx, fid in enumerate(labels):
                if block.field_type == "mcq":
                    correct_opt = str(expected_map.get(fid, block.options[0]))
                    if inject_hitl and f_idx == 2:
                        # Intentional double-marked bubble to demonstrate HITL review queue
                        alt = next(o for o in block.options if o != correct_opt)
                        answers[fid] = correct_opt + alt
                    elif rng.random() < 0.08:
                        answers[fid] = ""
                    elif rng.random() < skill:
                        answers[fid] = correct_opt
                    else:
                        wrongs = [o for o in block.options if o != correct_opt]
                        answers[fid] = rng.choice(wrongs)
                else:
                    answers[fid] = block.options[(idx + f_idx + 1) % len(block.options)]

        marked = render_synthetic_filled_sheet(
            blank, template, answers, mark_style=style, seed=700 + idx
        )
        distorted = apply_camera_distortion(
            marked,
            rotation_deg=rot,
            perspective_strength=persp,
            shadow_strength=shadow,
            seed=700 + idx,
        )
        res, warped = scanner.scan_image(distorted, source_name=f"{sid}.jpg")
        total_elapsed += res.elapsed_ms
        scanned_sheets.append(res)
        if warped is not None:
            wh, ww = warped.shape[:2]
            sheet_dimensions[res.sheet_id] = (ww, wh)
            overlays[res.sheet_id] = _encode_overlay(warped, res)
            crops = _extract_review_crops(warped, res)
            if crops:
                review_crops[res.sheet_id] = crops

    policy = GradingPolicy.preset("yks_tyt")
    report = ExamGrader(answer_key, policy).grade_batch(scanned_sheets)

    return {
        "template": template.model_dump(mode="json"),
        "answer_key": answer_key.model_dump(mode="json"),
        "scan_response": {
            "template_name": template.name,
            "total_sheets": len(scanned_sheets),
            "flagged_sheets": sum(1 for s in scanned_sheets if s.review_items),
            "failed_sheets": sum(1 for s in scanned_sheets if s.error is not None),
            "total_elapsed_ms": round(total_elapsed, 2),
            "sheets": [s.model_dump(mode="json") for s in scanned_sheets],
            "overlays": overlays,
            "review_crops": review_crops,
            "sheet_dimensions": sheet_dimensions,
        },
        "grading_report": report.model_dump(mode="json"),
    }


@router.post("/grade")
def grade_sheets(payload: GradeRequest) -> dict[str, Any]:
    """Grade scanned sheets and return student grades + Classical Test Theory psychometrics."""
    try:
        grader = ExamGrader(answer_key=payload.answer_key, policy=payload.policy)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid grading policy: {exc}") from exc
    report = grader.grade_batch(payload.sheets)
    return report.model_dump(mode="json")


@router.post("/export/csv")
def export_csv_endpoint(payload: ExportRequest) -> Response:
    """Export scan and optional grading results as downloadable CSV."""
    csv_text = export_csv_string(payload.sheets, report=payload.report)
    return Response(
        content=csv_text.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="omrkit_results.csv"'},
    )


@router.post("/export/xlsx")
def export_xlsx_endpoint(payload: ExportRequest) -> Response:
    """Export formatted multi-sheet Excel workbook."""
    try:
        data = export_excel_bytes(payload.sheets, report=payload.report)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="omrkit_report.xlsx"'},
    )


@router.post("/export/scorecard")
def export_scorecard_endpoint(payload: ScorecardRequest) -> Response:
    """Export a single student's printable A4 PDF scorecard."""
    pdf_bytes = export_pdf_scorecard_bytes(payload.grade, exam_name=payload.exam_name)
    safe_name = _safe_download_filename(payload.grade.sheet_id, "_scorecard.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )
