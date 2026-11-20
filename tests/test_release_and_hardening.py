"""Tests for public demo security headers, upload/page guardrails, and health metadata."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

from omrkit.api import create_app

client = TestClient(create_app())


def _make_blank_pdf(num_pages: int) -> bytes:
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    for i in range(num_pages):
        c.drawString(72, 720, f"Page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def test_security_headers_and_demo_mode_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMRKIT_DEMO_MODE", "true")
    monkeypatch.setenv("OMRKIT_MAX_UPLOAD_MB", "10")
    monkeypatch.setenv("OMRKIT_MAX_FILES_PER_SCAN", "8")
    monkeypatch.setenv("OMRKIT_MAX_PDF_PAGES", "12")

    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["demo_mode"] is True
    assert body["limits"] == {
        "max_upload_mb": 10,
        "max_files_per_scan": 8,
        "max_pdf_pages": 12,
    }
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=(self)" in res.headers["permissions-policy"]


def test_upload_size_limit_returns_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMRKIT_MAX_UPLOAD_MB", "1")
    oversized = b"\x00" * (1024 * 1024 + 64)

    prev = client.post(
        "/api/preview-image",
        files={"file": ("huge.jpg", oversized, "image/jpeg")},
    )
    assert prev.status_code == 413
    assert "exceeds maximum allowed upload size" in prev.json()["detail"]

    scan = client.post(
        "/api/scan",
        files=[("files", ("huge.jpg", oversized, "image/jpeg"))],
        data={"template_json": "auto"},
    )
    assert scan.status_code == 413


def test_max_files_and_max_pdf_pages_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMRKIT_MAX_FILES_PER_SCAN", "2")
    monkeypatch.setenv("OMRKIT_MAX_PDF_PAGES", "2")

    # 3 files exceeds max_files_per_scan=2
    too_many = client.post(
        "/api/scan",
        files=[
            ("files", ("a.jpg", b"123", "image/jpeg")),
            ("files", ("b.jpg", b"123", "image/jpeg")),
            ("files", ("c.jpg", b"123", "image/jpeg")),
        ],
        data={"template_json": "auto"},
    )
    assert too_many.status_code == 400
    assert "Too many files" in too_many.json()["detail"]

    # 3-page PDF exceeds max_pdf_pages=2
    pdf_3p = _make_blank_pdf(3)
    res_pdf = client.post(
        "/api/scan",
        files=[("files", ("multi.pdf", pdf_3p, "application/pdf"))],
        data={"template_json": "auto"},
    )
    assert res_pdf.status_code == 400
    assert "exceeding the configured limit of 2" in res_pdf.json()["detail"]
