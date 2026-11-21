"""End-to-end tests for OMRKit v2.3.0 Classroom & Teacher Workflows."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from omrkit.api.app import create_app
from omrkit.cli.app import app as cli_app
from omrkit.core.auto_scanner import scan_image_auto
from omrkit.core.scanner import OMRScanner
from omrkit.generator.pdf_sheet import SheetGenerator
from omrkit.generator.presets import get_sheet_preset
from omrkit.generator.roster import StudentRosterEntry, parse_roster_csv
from omrkit.grading.grader import ExamGrader
from omrkit.grading.key_extractor import extract_answer_key_from_sheets
from omrkit.io.exporters import (
    export_canvas_csv_string,
    export_merged_scorecards_pdf_bytes,
    export_moodle_csv_string,
    export_scorecards_zip_bytes,
)
from omrkit.io.loader import load_bytes
from omrkit.models.grading import GradingPolicy
from omrkit.models.template import BubbleCoord, Template
from omrkit.vision.qr import (
    encode_sheet_qr_payload,
    parse_sheet_qr_details,
    parse_sheet_qr_payload,
)


def _field_coords(template: Template) -> dict[str, list[BubbleCoord]]:
    return {fid: coords for blk in template.blocks for fid, coords in blk.iter_field_bubbles()}


def _fill_bubble(img: np.ndarray, cx: float, cy: float, radius: float, tone: int = 38) -> None:
    cv2.circle(img, (round(cx), round(cy)), max(2, round(radius * 0.78)), (tone, tone, tone), -1)


def test_qr_v2_and_v3_roundtrip_backward_compatibility() -> None:
    """Verify v2 preset-only QR stays backward compatible and v3 encodes Unicode student fields."""
    v2 = encode_sheet_qr_payload("standard_mcq_40")
    assert v2 == "OMRKIT:v2:standard_mcq_40"
    assert parse_sheet_qr_payload(v2) == "standard_mcq_40"
    v2_details = parse_sheet_qr_details(v2)
    assert v2_details is not None
    assert v2_details.version == "v2"
    assert not v2_details.has_student_metadata

    v3 = encode_sheet_qr_payload(
        "standard_mcq_40",
        student_id="20260042",
        student_name="Zeynep Yılmaz",  # noqa: RUF001
        classroom="12-A",
        booklet="b",
        email="zeynep@school.edu",
    )
    assert v3.startswith("OMRKIT:v3:standard_mcq_40|")
    assert parse_sheet_qr_payload(v3) == "standard_mcq_40"
    v3_details = parse_sheet_qr_details(v3)
    assert v3_details is not None
    assert v3_details.version == "v3"
    assert v3_details.has_student_metadata
    assert v3_details.student_id == "20260042"
    assert v3_details.student_name == "Zeynep Yılmaz"  # noqa: RUF001
    assert v3_details.classroom == "12-A"
    assert v3_details.booklet == "B"
    assert v3_details.email == "zeynep@school.edu"


def test_roster_csv_multilingual_headers_and_semicolons() -> None:
    """Parse semicolon-delimited Turkish/UTF-8 BOM CSV with split Ad/Soyad columns and enforce caps."""
    csv_text = (
        "\ufeffÖğrenci No;Ad;Soyad;Sınıf;Kitapçık;E-posta\n"  # noqa: RUF001
        "20260001;Ayşe;Demir;11-A;a;ayse@okul.edu.tr\n"
        "20260002;Can;Öztürk;11-B;B;can@okul.edu.tr\n"
    )
    entries = parse_roster_csv(csv_text)
    assert len(entries) == 2
    assert entries[0].student_id == "20260001"
    assert entries[0].name == "Ayşe Demir"
    assert entries[0].classroom == "11-A"
    assert entries[0].booklet == "A"
    assert entries[0].email == "ayse@okul.edu.tr"
    assert entries[1].name == "Can Öztürk"

    with pytest.raises(ValueError, match="maximum allowed limit"):
        parse_roster_csv(csv_text, max_students=1)


def test_roster_mail_merge_packet_prefill_and_qr_v3_auto_scan_end_to_end() -> None:
    """Generate a personalized 3-student PDF packet and verify QR v3 + pre-filled IDs scan accurately."""
    spec = get_sheet_preset("standard_mcq_40")
    students = [
        StudentRosterEntry(
            student_id="20260001",
            name="Zeynep Kaya",
            classroom="12-A",
            booklet="A",
            email="zeynep@school.edu",
        ),
        StudentRosterEntry(
            student_id="20260002",
            name="Lukas Weber",
            classroom="12-B",
            booklet="B",
            email="lukas@school.edu",
        ),
        StudentRosterEntry(
            student_id="20260003",
            name="Lin Wei",
            classroom="12-A",
            booklet="A",
            email="lin@school.edu",
        ),
    ]

    # 1. Pre-filled ID & Booklet bubbles
    packet = SheetGenerator().generate_roster_packet(spec, students, pre_fill_id=True)
    pages = load_bytes(packet.pdf_bytes, "class_packet.pdf", dpi=200)
    assert len(pages) == 3

    template = packet.template
    coords = _field_coords(template)

    # Mark Q1..Q5 on page 0 and scan via zero-template QR auto-scanner
    p0 = pages[0].image_bgr.copy()
    for q_idx, opt in enumerate(("A", "B", "C", "D", "E"), start=1):
        for c in coords[f"q{q_idx}"]:
            if c.option == opt:
                _fill_bubble(p0, c.cx, c.cy, c.radius)

    auto_res, _ = scan_image_auto(p0, source_name="p0.jpg")
    assert auto_res.error is None
    assert auto_res.grouped_values["STUDENT_ID"] == "20260001"
    assert auto_res.grouped_values["STUDENT_NAME"] == "Zeynep Kaya"
    assert auto_res.grouped_values["CLASSROOM"] == "12-A"
    assert auto_res.grouped_values["EMAIL"] == "zeynep@school.edu"
    assert auto_res.fields["BOOKLET"].value == "A"
    assert auto_res.fields["q1"].value == "A"
    assert auto_res.fields["q5"].value == "E"

    # Scan page 1 with explicit OMRScanner(template) — should STILL decode QR v3 student metadata!
    explicit_res, _ = OMRScanner(template).scan_image(pages[1].image_bgr, source_name="p1.jpg")
    assert explicit_res.error is None
    assert explicit_res.grouped_values["STUDENT_ID"] == "20260002"
    assert explicit_res.grouped_values["STUDENT_NAME"] == "Lukas Weber"
    assert explicit_res.grouped_values["CLASSROOM"] == "12-B"
    assert explicit_res.fields["BOOKLET"].value == "B"

    # 2. Without pre-fill: ID & Booklet bubbles are blank, QR v3 fills them cleanly without errors
    packet_no_prefill = SheetGenerator().generate_roster_packet(
        spec, [students[1]], pre_fill_id=False
    )
    blank_page = load_bytes(packet_no_prefill.pdf_bytes, "no_prefill.pdf", dpi=200)[0].image_bgr
    res_qr_only, _ = OMRScanner(packet_no_prefill.template).scan_image(
        blank_page, source_name="qr_only.jpg"
    )
    assert res_qr_only.grouped_values["STUDENT_ID"] == "20260002"
    assert res_qr_only.grouped_values["STUDENT_NAME"] == "Lukas Weber"
    assert res_qr_only.fields["BOOKLET"].value == "B"
    assert not any(r.field_id == "STUDENT_ID" for r in res_qr_only.review_items)


def test_zero_json_teacher_key_sheet_multi_booklet_and_lms_exports() -> None:
    """Extract multi-booklet AnswerKey from teacher sheets, grade roster sheets, and test LMS + PDF exports."""
    spec = get_sheet_preset("standard_mcq_40")
    generated = SheetGenerator().generate(spec)
    template = generated.template
    blank = load_bytes(generated.pdf_bytes, "blank.pdf", dpi=200)[0].image_bgr
    coords = _field_coords(template)
    scanner = OMRScanner(template)

    # Teacher marks Booklet A (q3 multi-answer A+C, q40 left blank)
    key_a_img = blank.copy()
    for c in coords["BOOKLET"]:
        if c.option == "A":
            _fill_bubble(key_a_img, c.cx, c.cy, c.radius)
    for q_idx in range(1, 40):  # intentionally leave q40 blank
        qid = f"q{q_idx}"
        opts_to_fill = ["A", "C"] if q_idx == 3 else [spec.options[(q_idx - 1) % 5]]
        for c in coords[qid]:
            if c.option in opts_to_fill:
                _fill_bubble(key_a_img, c.cx, c.cy, c.radius)

    # Teacher marks Booklet B (shifted answers)
    key_b_img = blank.copy()
    for c in coords["BOOKLET"]:
        if c.option == "B":
            _fill_bubble(key_b_img, c.cx, c.cy, c.radius)
    for q_idx in range(1, 41):
        qid = f"q{q_idx}"
        opt = spec.options[q_idx % 5]
        for c in coords[qid]:
            if c.option == opt:
                _fill_bubble(key_b_img, c.cx, c.cy, c.radius)

    sheet_a, _ = scanner.scan_image(key_a_img, source_name="key_A.jpg")
    sheet_b, _ = scanner.scan_image(key_b_img, source_name="key_B.jpg")

    extracted = extract_answer_key_from_sheets(
        [sheet_a, sheet_b], template=template, exam_name="Midterm Biology"
    )
    assert extracted.booklets_detected == ["A", "B"]
    assert extracted.questions_count == 40
    assert extracted.answer_key.booklets["A"]["q3"] == ["A", "C"]
    assert "A:q40" in extracted.blank_questions
    assert "A:q3" in extracted.multi_answer_questions

    # Grade two personalized students (one Booklet A, one Booklet B) against the extracted key
    roster = [
        StudentRosterEntry(
            student_id="10000001",
            name="Ada Lovelace",
            classroom="CS-101",
            booklet="A",
            email="ada@uni.edu",
        ),
        StudentRosterEntry(
            student_id="10000002",
            name="Alan Turing",
            classroom="CS-101",
            booklet="B",
            email="alan@uni.edu",
        ),
    ]
    packet = SheetGenerator().generate_roster_packet(spec, roster, pre_fill_id=True)
    student_pages = load_bytes(packet.pdf_bytes, "students.pdf", dpi=200)

    # Ada marks C on q3 (should be marked correct under multi-answer A/C!) and matches rest of A
    s0 = student_pages[0].image_bgr.copy()
    for q_idx in range(1, 40):
        opt = "C" if q_idx == 3 else spec.options[(q_idx - 1) % 5]
        for c in coords[f"q{q_idx}"]:
            if c.option == opt:
                _fill_bubble(s0, c.cx, c.cy, c.radius)

    # Alan matches all 40 of Booklet B
    s1 = student_pages[1].image_bgr.copy()
    for q_idx in range(1, 41):
        opt = spec.options[q_idx % 5]
        for c in coords[f"q{q_idx}"]:
            if c.option == opt:
                _fill_bubble(s1, c.cx, c.cy, c.radius)

    res0, _ = scanner.scan_image(s0, source_name="ada.jpg")
    res1, _ = scanner.scan_image(s1, source_name="alan.jpg")

    report = ExamGrader(extracted.answer_key, GradingPolicy.preset("standard")).grade_batch(
        [res0, res1]
    )
    assert report.grades[0].correct == 39
    assert report.grades[1].correct == 40

    # Moodle CSV verification
    moodle_rows = list(csv.reader(io.StringIO(export_moodle_csv_string(report))))
    assert moodle_rows[0] == [
        "Identifier",
        "Full name",
        "ID number",
        "Email address",
        "Grade",
        "Maximum Grade",
        "Feedback comments",
    ]
    assert moodle_rows[1][1] == "Ada Lovelace"
    assert moodle_rows[1][2] == "10000001"
    assert moodle_rows[1][3] == "ada@uni.edu"
    assert moodle_rows[1][4] == "39.00"
    assert moodle_rows[2][1] == "Alan Turing"
    assert moodle_rows[2][4] == "40.00"

    # Canvas CSV verification
    canvas_rows = list(csv.reader(io.StringIO(export_canvas_csv_string(report))))
    assert canvas_rows[0] == [
        "Student",
        "ID",
        "SIS User ID",
        "SIS Login ID",
        "Section",
        "Midterm Biology",
    ]
    assert canvas_rows[1][0] == "    Points Possible"
    assert canvas_rows[1][5] == "40.00"
    assert canvas_rows[2][0] == "Ada Lovelace"
    assert canvas_rows[2][4] == "CS-101"
    assert canvas_rows[2][5] == "39.00"

    # Merged Class Scorecards PDF & ZIP verification
    merged_pdf = export_merged_scorecards_pdf_bytes(report)
    assert merged_pdf.startswith(b"%PDF-")
    merged_pages = load_bytes(merged_pdf, "merged.pdf", dpi=100)
    assert len(merged_pages) == 2

    zip_bytes = export_scorecards_zip_bytes(report)
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        names = zf.namelist()
        assert len(names) == 2
        assert all(n.endswith("_scorecard.pdf") for n in names)


def test_v23_cli_generate_roster_key_from_sheet_and_watch(tmp_path: Path) -> None:
    """Test CLI commands: generate --roster, key-from-sheet, and watch --max-cycles 1."""
    runner = CliRunner()

    roster_csv = tmp_path / "class.csv"
    roster_csv.write_text(
        "student_id,name,classroom,booklet\n123456,Deniz Aydın,10-A,A\n",  # noqa: RUF001
        encoding="utf-8",
    )

    gen_dir = tmp_path / "gen_out"
    res_gen = runner.invoke(
        cli_app,
        [
            "generate",
            "--preset",
            "quick_quiz_20",
            "--roster",
            str(roster_csv),
            "-o",
            str(gen_dir),
        ],
    )
    assert res_gen.exit_code == 0, res_gen.output
    packet_pdf = gen_dir / "quick_quiz_20_roster_packet.pdf"
    assert packet_pdf.is_file()

    # Create a teacher-marked key image from the generated quick_quiz_20 blank
    tmpl = Template.from_file(gen_dir / "template.json")
    blank = load_bytes(packet_pdf.read_bytes(), "packet.pdf", dpi=200)[0].image_bgr
    coords = _field_coords(tmpl)
    key_img = blank.copy()
    for q_idx in range(1, 21):
        opt = ["A", "B", "C", "D"][(q_idx - 1) % 4]
        for c in coords[f"q{q_idx}"]:
            if c.option == opt:
                _fill_bubble(key_img, c.cx, c.cy, c.radius)

    key_img_path = tmp_path / "teacher_key.jpg"
    cv2.imwrite(str(key_img_path), key_img)

    extracted_key_path = tmp_path / "extracted_key.json"
    res_key = runner.invoke(
        cli_app,
        [
            "key-from-sheet",
            str(key_img_path),
            "-o",
            str(extracted_key_path),
            "--exam-name",
            "Quiz 1",
        ],
    )
    assert res_key.exit_code == 0, res_key.output
    assert extracted_key_path.is_file()
    key_data = json.loads(extracted_key_path.read_text(encoding="utf-8"))
    assert key_data["answers"]["q1"] == "A"
    assert key_data["answers"]["q20"] == "D"

    # Watch inbox folder for 1 finite poll cycle
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    cv2.imwrite(str(inbox / "student_1.jpg"), key_img)
    watch_out = tmp_path / "watch_out"
    res_watch = runner.invoke(
        cli_app,
        [
            "watch",
            str(inbox),
            "-k",
            str(extracted_key_path),
            "-o",
            str(watch_out),
            "--max-cycles",
            "1",
            "--interval",
            "0.1",
        ],
    )
    assert res_watch.exit_code == 0, res_watch.output
    assert (watch_out / "results.csv").is_file()
    assert (watch_out / "moodle_grades.csv").is_file()
    assert (watch_out / "canvas_grades.csv").is_file()


def test_v23_api_endpoints_roster_key_and_lms_exports() -> None:
    """Verify /api/generate/roster-packet, /api/answer-key/from-sheet, and LMS/merged PDF export APIs."""
    client = TestClient(create_app())
    spec = get_sheet_preset("quick_quiz_20")

    # 1. Roster packet endpoint
    roster_res = client.post(
        "/api/generate/roster-packet",
        data={
            "spec_json": json.dumps(spec.model_dump(mode="json")),
            "roster_csv": "student_id,name,classroom\n111111,Ali Veli,9-A\n222222,Sara Kim,9-B\n",
            "pre_fill_id": "true",
        },
    )
    assert roster_res.status_code == 200
    assert roster_res.headers["content-type"] == "application/pdf"
    assert roster_res.headers["x-omrkit-student-count"] == "2"
    assert roster_res.content.startswith(b"%PDF-")

    # 2. Zero-JSON teacher answer-key extraction via API (QR auto mode)
    generated = SheetGenerator().generate(spec)
    blank = load_bytes(generated.pdf_bytes, "blank.pdf", dpi=200)[0].image_bgr
    coords = _field_coords(generated.template)
    for q_idx in range(1, 21):
        opt = spec.options[(q_idx - 1) % len(spec.options)]
        for c in coords[f"q{q_idx}"]:
            if c.option == opt:
                _fill_bubble(blank, c.cx, c.cy, c.radius)
    ok, encoded = cv2.imencode(".jpg", blank)
    assert ok

    key_res = client.post(
        "/api/answer-key/from-sheet",
        data={"template_json": "auto", "exam_name": "API Scanned Key"},
        files=[("files", ("key_sheet.jpg", encoded.tobytes(), "image/jpeg"))],
    )
    assert key_res.status_code == 200
    key_body = key_res.json()
    assert key_body["questions_count"] == 20
    assert key_body["answer_key"]["answers"]["q1"] == "A"

    # Security guardrail: marker_path blocked on /api/answer-key/from-sheet too
    bad_tmpl = generated.template.model_dump(mode="json")
    bad_tmpl["registration"]["marker_path"] = "/etc/passwd"
    sec_res = client.post(
        "/api/answer-key/from-sheet",
        data={"template_json": json.dumps(bad_tmpl)},
        files=[("files", ("key_sheet.jpg", encoded.tobytes(), "image/jpeg"))],
    )
    assert sec_res.status_code == 400

    # 3. Export Moodle CSV, Canvas CSV, and Merged Class Scorecards PDF from demo cohort
    demo = client.post("/api/demo/cohort?preset_id=quick_quiz_20").json()
    export_payload = {
        "sheets": demo["scan_response"]["sheets"],
        "report": demo["grading_report"],
    }

    moodle_res = client.post("/api/export/moodle", json=export_payload)
    assert moodle_res.status_code == 200
    assert "Feedback comments" in moodle_res.text

    canvas_res = client.post("/api/export/canvas", json=export_payload)
    assert canvas_res.status_code == 200
    assert "Points Possible" in canvas_res.text

    merged_res = client.post("/api/export/scorecards-pdf", json=export_payload)
    assert merged_res.status_code == 200
    assert merged_res.content.startswith(b"%PDF-")
    assert len(load_bytes(merged_res.content, "cards.pdf", dpi=100)) == 5
