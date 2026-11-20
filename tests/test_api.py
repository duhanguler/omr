"""End-to-end FastAPI REST API and compiled Web Studio tests."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from omrkit.api import create_app

client = TestClient(create_app())


def test_health_root_and_presets() -> None:
    root = client.get("/")
    assert root.status_code == 200
    assert "OMRKit Studio" in root.text

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    presets = client.get("/api/presets")
    assert presets.status_code == 200
    payload = presets.json()
    ids = {p["id"] for p in payload["sheet_presets"]}
    assert {"quick_quiz_20", "standard_mcq_40", "turkish_exam_50", "turkish_yks_120"} <= ids


def test_generate_and_bundle_endpoints() -> None:
    presets = client.get("/api/presets").json()
    spec = presets["sheet_presets"][0]["spec"]

    gen = client.post("/api/generate", json=spec)
    assert gen.status_code == 200
    data = gen.json()
    assert data["pdf_base64"]
    assert data["preview_data_url"].startswith("data:image/jpeg;base64,")

    bundle = client.post("/api/generate/bundle", json=spec)
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
        names = set(zf.namelist())
        assert "template.json" in names
        assert "answer_key.json" in names


def test_scan_grade_and_export_endpoints() -> None:
    template_json = Path("examples/quick_quiz_20q/template.json").read_text(encoding="utf-8")
    answer_key = json.loads(
        Path("examples/quick_quiz_20q/answer_key.json").read_text(encoding="utf-8")
    )
    sample_img = Path("examples/quick_quiz_20q/scans/student_01_clean.jpg").read_bytes()

    # Validate template
    val = client.post("/api/templates/validate", json=json.loads(template_json))
    assert val.status_code == 200
    assert val.json()["valid"] is True

    # Preview image
    prev = client.post(
        "/api/preview-image",
        files={"file": ("student_01_clean.jpg", sample_img, "image/jpeg")},
    )
    assert prev.status_code == 200
    assert prev.json()["width"] > 0

    # Scan
    scan = client.post(
        "/api/scan",
        files=[("files", ("student_01_clean.jpg", sample_img, "image/jpeg"))],
        data={"template_json": template_json, "include_overlay": "true"},
    )
    assert scan.status_code == 200
    scan_data = scan.json()
    assert scan_data["total_sheets"] == 1
    assert scan_data["failed_sheets"] == 0
    assert len(scan_data["overlays"]) == 1

    # Grade
    grade = client.post(
        "/api/grade",
        json={
            "sheets": scan_data["sheets"],
            "answer_key": answer_key,
            "policy": {"name": "standard", "correct_points": 1.0, "incorrect_points": 0.0},
        },
    )
    assert grade.status_code == 200
    report = grade.json()
    assert report["analytics"]["student_count"] == 1

    # Exports (CSV, XLSX, PDF Scorecard)
    csv_res = client.post("/api/export/csv", json={"sheets": scan_data["sheets"], "report": report})
    assert csv_res.status_code == 200
    assert "student_01_clean" in csv_res.text

    xlsx_res = client.post(
        "/api/export/xlsx", json={"sheets": scan_data["sheets"], "report": report}
    )
    assert xlsx_res.status_code == 200
    assert xlsx_res.content[:2] == b"PK"

    card_res = client.post(
        "/api/export/scorecard",
        json={"grade": report["grades"][0], "exam_name": report["exam_name"]},
    )
    assert card_res.status_code == 200
    assert card_res.content.startswith(b"%PDF")
