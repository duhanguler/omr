"""FastAPI REST API routes powering OMRKit Web Studio and third-party integrations."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from omrkit.core.scanner import OMRScanner
from omrkit.generator.pdf_sheet import SheetGenerator
from omrkit.generator.presets import SheetSpec, get_sheet_presets
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
from omrkit.vision.visualizer import render_annotated_sheet

router = APIRouter(prefix="/api", tags=["omrkit"])


def _encode_image_data_url(image_bgr: np.ndarray, fmt: str = ".jpg", quality: int = 86) -> str:
    params = [cv2.IMWRITE_JPEG_QUALITY, quality] if fmt == ".jpg" else []
    ok, encoded = cv2.imencode(fmt, image_bgr, params)
    if not ok:
        raise RuntimeError("Failed to encode image buffer.")
    mime = "image/jpeg" if fmt == ".jpg" else "image/png"
    b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


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


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return service health and package version."""
    return {"status": "ok", "service": "omrkit", "version": "2.0.0"}


@router.get("/presets")
def list_presets() -> dict[str, Any]:
    """Return built-in optical sheet presets (with exact templates) and grading policies."""
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


@router.post("/generate")
def generate_sheet(spec: SheetSpec) -> dict[str, Any]:
    """Generate a printable PDF (base64), matching exact Template, and sample AnswerKey."""
    generated = SheetGenerator().generate(spec)
    pdf_b64 = base64.b64encode(generated.pdf_bytes).decode("ascii")
    preview_page = load_bytes(generated.pdf_bytes, f"{spec.preset_id}.pdf", dpi=140)[0]
    return {
        "filename": f"{spec.preset_id}_sheet.pdf",
        "pdf_base64": pdf_b64,
        "preview_data_url": _encode_image_data_url(preview_page.image_bgr, fmt=".jpg", quality=88),
        "template": generated.template.model_dump(mode="json"),
        "sample_answer_key": generated.sample_answer_key.model_dump(mode="json"),
    }


@router.post("/generate/bundle")
def generate_sheet_bundle(spec: SheetSpec) -> Response:
    """Download a ZIP archive containing the PDF sheet, template.json, and answer_key.json."""
    generated = SheetGenerator().generate(spec)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{spec.preset_id}_sheet.pdf", generated.pdf_bytes)
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
        headers={"Content-Disposition": f'attachment; filename="{spec.preset_id}_bundle.zip"'},
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


@router.post("/preview-image")
async def preview_uploaded_document(
    file: UploadFile = File(...),
    dpi: int = Form(200),
) -> dict[str, Any]:
    """Decode any uploaded image or PDF first page for the Visual Template Designer canvas."""
    data = await file.read()
    try:
        pages = load_bytes(data, filename=file.filename or "upload.png", dpi=dpi)
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
    template_json: str = Form(...),
    include_overlay: bool = Form(True),
    dpi: int = Form(200),
) -> dict[str, Any]:
    """Scan one or more uploaded images/PDFs against the supplied template JSON."""
    try:
        template = Template.model_validate(json.loads(template_json))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid template JSON: {exc}") from exc

    scanner = OMRScanner(template=template, dpi=dpi)
    sheets: list[dict[str, Any]] = []
    overlays: dict[str, str] = {}
    total_elapsed = 0.0
    flagged_count = 0
    failed_count = 0

    for upload in files:
        raw_bytes = await upload.read()
        fname = upload.filename or "sheet.png"
        try:
            page_results = scanner.scan_bytes(raw_bytes, filename=fname)
        except DocumentLoadError as exc:
            failed_count += 1
            sheets.append(
                SheetResult(
                    sheet_id=fname,
                    source_file=fname,
                    template_name=template.name,
                    overall_confidence=0.0,
                    registration_method=template.registration.mode,
                    registration_score=0.0,
                    error=str(exc),
                ).model_dump(mode="json")
            )
            continue

        for result, warped_bgr in page_results:
            total_elapsed += result.elapsed_ms
            if result.error is not None:
                failed_count += 1
            elif result.review_items:
                flagged_count += 1
            sheets.append(result.model_dump(mode="json"))

            if include_overlay and warped_bgr is not None:
                annotated = render_annotated_sheet(warped_bgr, result)
                # Downscale overlay gently if huge to keep JSON responses snappy
                h, w = annotated.shape[:2]
                if max(h, w) > 1600:
                    scale = 1600.0 / float(max(h, w))
                    annotated = cv2.resize(
                        annotated,
                        (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA,
                    )
                overlays[result.sheet_id] = _encode_image_data_url(
                    annotated, fmt=".jpg", quality=85
                )

    return {
        "template_name": template.name,
        "total_sheets": len(sheets),
        "flagged_sheets": flagged_count,
        "failed_sheets": failed_count,
        "total_elapsed_ms": round(total_elapsed, 2),
        "sheets": sheets,
        "overlays": overlays,
    }


@router.post("/grade")
def grade_sheets(payload: GradeRequest) -> dict[str, Any]:
    """Grade scanned sheets and return student grades + Classical Test Theory psychometrics."""
    grader = ExamGrader(answer_key=payload.answer_key, policy=payload.policy)
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
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{payload.grade.sheet_id}_scorecard.pdf"'
        },
    )
