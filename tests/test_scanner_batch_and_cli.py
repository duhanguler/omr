"""Tests for batch scanning, multi-page PDF handling, and Typer CLI commands."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from typer.testing import CliRunner

from omrkit.cli.app import app
from omrkit.core.benchmark import render_synthetic_filled_sheet
from omrkit.core.scanner import OMRScanner
from omrkit.generator import SheetGenerator, get_sheet_preset
from omrkit.io.loader import load_bytes

runner = CliRunner()


def test_multipage_pdf_and_corrupt_file_handling(tmp_path: Path) -> None:
    spec = get_sheet_preset("quick_quiz_20")
    gen = SheetGenerator().generate(spec)
    blank = load_bytes(gen.pdf_bytes, "quiz.pdf", dpi=spec.dpi)[0].image_bgr

    # Build a 2-page PDF with two different marked sheets
    pdf_path = tmp_path / "batch_2pages.pdf"
    c = rl_canvas.Canvas(str(pdf_path), pagesize=A4)
    w, h = A4
    expected_pages = [{"q1": "A", "q2": "B"}, {"q1": "D", "q2": "C"}]
    for idx, ans in enumerate(expected_pages):
        marked = render_synthetic_filled_sheet(blank, gen.template, ans, seed=50 + idx)
        rgb = marked[:, :, ::-1]
        img_buf = io.BytesIO()
        Image.fromarray(rgb).save(img_buf, format="JPEG", quality=92)
        img_buf.seek(0)
        c.drawImage(ImageReader(img_buf), 0, 0, width=w, height=h)
        c.showPage()
    c.save()

    # Also drop a corrupt image in the same directory
    (tmp_path / "corrupt.jpg").write_bytes(b"not-a-valid-jpeg")

    batch = OMRScanner(gen.template).scan_batch(tmp_path, workers=1)
    assert batch.total_sheets == 3
    assert batch.succeeded == 2
    assert batch.failed_sheets == 1

    valid = [s for s in batch.sheets if s.error is None]
    assert valid[0].fields["q1"].value == "A"
    assert valid[0].fields["q2"].value == "B"
    assert valid[1].fields["q1"].value == "D"
    assert valid[1].fields["q2"].value == "C"


def test_cli_generate_validate_scan_grade_pipeline(tmp_path: Path) -> None:
    list_res = runner.invoke(app, ["generate", "--list"])
    assert list_res.exit_code == 0
    assert "standard_mcq_40" in list_res.output

    gen_dir = tmp_path / "generated"
    gen_res = runner.invoke(app, ["generate", "--preset", "quick_quiz_20", "-o", str(gen_dir)])
    assert gen_res.exit_code == 0
    tmpl_file = gen_dir / "template.json"
    key_file = gen_dir / "answer_key.json"
    assert tmpl_file.exists() and key_file.exists()

    val_res = runner.invoke(app, ["validate", str(tmpl_file)])
    assert val_res.exit_code == 0
    assert "Valid OMRKit" in val_res.output

    out_dir = tmp_path / "scan_out"
    scan_res = runner.invoke(
        app,
        [
            "scan",
            "examples/quick_quiz_20q/scans",
            "-t",
            "examples/quick_quiz_20q/template.json",
            "-k",
            "examples/quick_quiz_20q/answer_key.json",
            "--policy",
            "yks_tyt",
            "-o",
            str(out_dir),
            "--format",
            "csv,json,xlsx,scorecards",
        ],
    )
    assert scan_res.exit_code == 0
    assert (out_dir / "results.csv").exists()
    assert (out_dir / "results.json").exists()
    assert (out_dir / "report.xlsx").exists()
    assert (out_dir / "scorecards").exists()

    grade_out = tmp_path / "regraded"
    grade_res = runner.invoke(
        app,
        [
            "grade",
            str(out_dir / "results.json"),
            "-k",
            "examples/quick_quiz_20q/answer_key.json",
            "--policy",
            "lgs",
            "-o",
            str(grade_out),
        ],
    )
    assert grade_res.exit_code == 0
    assert (grade_out / "graded_report.json").exists()
