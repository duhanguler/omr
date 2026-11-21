"""Regression tests for the 16 bugs fixed in OMRKit v2.3.1."""

from __future__ import annotations

import base64
import csv
import io
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from omrkit.api.app import create_app
from omrkit.cli.app import app as cli_app
from omrkit.core.auto_scanner import scan_image_auto
from omrkit.core.benchmark import apply_camera_distortion
from omrkit.core.scanner import OMRScanner
from omrkit.generator.pdf_sheet import SheetGenerator
from omrkit.generator.presets import get_sheet_preset
from omrkit.generator.roster import StudentRosterEntry
from omrkit.grading.grader import ExamGrader
from omrkit.grading.key_extractor import extract_answer_key_from_sheets
from omrkit.io.exporters import (
    export_canvas_csv_string,
    export_csv_string,
    export_excel_bytes,
    export_moodle_csv_string,
)
from omrkit.io.loader import load_bytes
from omrkit.models.grading import GradingPolicy
from omrkit.vision.registration import RegistrationError, register_sheet


def test_qr_v3_long_turkish_chinese_russian_names_200dpi_and_distorted() -> None:
    """Bug #1: Raw-UTF8 byte-budgeted QR v3 decodes reliably across TR, ZH, RU, distortion, and LETTER."""
    spec = get_sheet_preset("standard_mcq_40")
    students = [
        StudentRosterEntry(
            student_id="20260001",
            name="Abdurrahman Şemseddin Çelikkol",
            classroom="12-MF-A",
            booklet="A",
            email="abdurrahman.celikkol@university.edu.tr",
        ),
        StudentRosterEntry(
            student_id="20260002",
            name="欧阳明月同学测试姓名很长",
            classroom="高三2班",
            booklet="B",
            email="ouyang.mingyue@school.edu.cn",
        ),
        StudentRosterEntry(
            student_id="20260003",
            name="Александр Константинопольский",
            classroom="11-Б",
            booklet="C",
            email="alex.konstantinopolsky@school.ru",
        ),
    ]
    packet = SheetGenerator().generate_roster_packet(spec, students, pre_fill_id=True)
    pages = load_bytes(packet.pdf_bytes, "unicode_roster.pdf", dpi=200)
    scanner = OMRScanner(packet.template)

    for idx, (st, page) in enumerate(zip(students, pages, strict=True)):
        res_clean, _ = scanner.scan_image(page.image_bgr, source_name=f"clean_{idx}.jpg")
        assert res_clean.error is None
        assert res_clean.grouped_values.get("STUDENT_NAME")
        assert st.name.startswith(res_clean.grouped_values["STUDENT_NAME"])
        assert res_clean.grouped_values["STUDENT_ID"] == st.student_id

        dist = apply_camera_distortion(
            page.image_bgr,
            rotation_deg=90,
            perspective_strength=0.025,
            shadow_strength=0.20,
            seed=42 + idx,
        )
        res_dist, _ = scanner.scan_image(dist, source_name=f"dist_{idx}.jpg")
        assert res_dist.error is None
        assert res_dist.grouped_values.get("STUDENT_NAME")

        res_auto, _ = scan_image_auto(dist, source_name=f"auto_{idx}.jpg")
        assert res_auto.error is None
        assert res_auto.grouped_values.get("STUDENT_NAME")

    # Verify LETTER page format with 90° rotation decodes v3 QR cleanly too
    letter_spec = spec.model_copy(update={"page_format": "LETTER"})
    lp = SheetGenerator().generate_roster_packet(letter_spec, [students[0]], pre_fill_id=True)
    l_img = load_bytes(lp.pdf_bytes, "letter.pdf", dpi=200)[0].image_bgr
    l_rot = cv2.rotate(l_img, cv2.ROTATE_90_CLOCKWISE)
    l_res, _ = OMRScanner(lp.template).scan_image(l_rot, source_name="letter_rot.jpg")
    assert l_res.error is None
    assert l_res.grouped_values.get("STUDENT_NAME")


def test_spreadsheet_formula_injection_and_excel_illegal_control_chars() -> None:
    """Bugs #2 & #8: Neutralize formula prefixes, strip Excel illegal chars, deduplicate BOOKLET col."""
    spec = get_sheet_preset("standard_mcq_40")
    gen = SheetGenerator().generate(spec)
    blank = load_bytes(gen.pdf_bytes, "b.pdf", dpi=200)[0].image_bgr
    sheet, _ = OMRScanner(gen.template).scan_image(blank, source_name="=evil_file.jpg")

    sheet.grouped_values["BOOKLET"] = "A"
    sheet.grouped_values["STUDENT_NAME"] = "=CMD|' /C calc'!A0\x07"
    sheet.grouped_values["STUDENT_ID"] = "+2+5"
    sheet.grouped_values["CLASSROOM"] = "@SUM(A1:A5)"

    # Grade with negative marking so numeric negative scores remain untouched
    # Mark q1 wrong so YKS policy produces negative score (-0.25)
    sheet.apply_override("q1", "E")
    report = ExamGrader(gen.sample_answer_key, GradingPolicy.preset("yks_tyt")).grade_batch([sheet])
    assert report.grades[0].raw_score < 0

    csv_text = export_csv_string([sheet], report=report)
    rows = list(csv.reader(io.StringIO(csv_text)))
    assert rows[0].count("BOOKLET") == 1
    assert rows[1][1].startswith("'=evil_file.jpg")
    name_col = rows[0].index("STUDENT_NAME")
    assert rows[1][name_col] == "'=CMD|' /C calc'!A0"
    score_col = rows[0].index("score")
    assert float(rows[1][score_col]) < 0  # numeric negative score NOT escaped

    # Moodle & Canvas formula neutralization
    moodle_rows = list(csv.reader(io.StringIO(export_moodle_csv_string(report))))
    assert moodle_rows[1][1] == "'=CMD|' /C calc'!A0"
    assert float(moodle_rows[1][4]) < 0

    canvas_rows = list(csv.reader(io.StringIO(export_canvas_csv_string(report))))
    assert canvas_rows[2][0] == "'=CMD|' /C calc'!A0"
    assert float(canvas_rows[2][5]) < 0

    # Excel export must NOT crash with IllegalCharacterError
    xlsx_bytes = export_excel_bytes([sheet], report=report)
    assert xlsx_bytes[:2] == b"PK"


def test_aruco_duplicate_noise_marker_and_degenerate_3pt_rejected() -> None:
    """Bugs #3 & #4: Ignore tiny duplicate ArUco ID noise and reject degenerate 3-marker homographies."""
    spec = get_sheet_preset("standard_mcq_40")
    gen = SheetGenerator().generate(spec)
    blank = load_bytes(gen.pdf_bytes, "b.pdf", dpi=200)[0].image_bgr
    h, _w = blank.shape[:2]
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    # Bug #4: Small 28px duplicate ID 0 in page center must NOT overwrite real TL corner marker
    img_dup = blank.copy()
    tiny_m0 = cv2.aruco.generateImageMarker(aruco_dict, 0, 28)
    tiny_m0 = cv2.copyMakeBorder(tiny_m0, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    img_dup[1100:1136, 800:836] = cv2.cvtColor(tiny_m0, cv2.COLOR_GRAY2BGR)
    reg = register_sheet(img_dup, gen.template)
    assert reg.method == "aruco"
    assert reg.source_corners is not None
    tl_x, tl_y = reg.source_corners[0]
    assert tl_x < 250 and tl_y < 250

    # Bug #3: Missing bottom two markers + tiny fake ID 2 must raise RegistrationError
    img_bad3 = blank.copy()
    img_bad3[h - 240 : h, :] = 255
    tiny_m2 = cv2.aruco.generateImageMarker(aruco_dict, 2, 32)
    tiny_m2 = cv2.copyMakeBorder(tiny_m2, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    img_bad3[300:340, 300:340] = cv2.cvtColor(tiny_m2, cv2.COLOR_GRAY2BGR)
    with pytest.raises(RegistrationError):
        register_sheet(img_bad3, gen.template)


def test_auto_detect_returns_aligned_deskewed_image_matching_coordinates() -> None:
    """Bug #5: /api/templates/auto-detect returns the deskewed image aligned to detected coordinates."""
    client = TestClient(create_app())
    spec = get_sheet_preset("standard_mcq_40")
    gen = SheetGenerator().generate(spec)
    blank = load_bytes(gen.pdf_bytes, "b.pdf", dpi=200)[0].image_bgr
    h, w = blank.shape[:2]
    rot_m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 3.0, 1.0)
    tilted = cv2.warpAffine(blank, rot_m, (w, h), borderValue=(255, 255, 255))
    ok, encoded = cv2.imencode(".jpg", tilted)
    assert ok

    res = client.post(
        "/api/templates/auto-detect",
        files={"file": ("tilted_blank.jpg", encoded.tobytes(), "image/jpeg")},
    )
    assert res.status_code == 200
    body = res.json()
    assert abs(body["template"]["metadata"]["deskew_deg"]) >= 2.0

    # Verify returned preview image differs from the tilted input (i.e. it was deskewed)
    b64_img = body["image_data_url"].split(",", 1)[1]
    returned_arr = cv2.imdecode(
        np.frombuffer(base64.b64decode(b64_img), np.uint8), cv2.IMREAD_COLOR
    )
    assert returned_arr is not None
    diff_mean = float(np.mean(np.abs(returned_arr.astype(np.float32) - tilted.astype(np.float32))))
    assert diff_mean > 5.0


def test_watch_and_auto_scan_survive_corrupt_half_written_files(tmp_path: Path) -> None:
    """Bug #6: Neither omrkit watch nor QR-auto omrkit scan crashes on corrupt/half-written files."""
    runner = CliRunner()
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    # Drop one corrupt half-written JPEG alongside one valid sheet
    (inbox / "half_written.jpg").write_bytes(b"\xff\xd8\xff\xe0TRUNCATED")
    spec = get_sheet_preset("quick_quiz_20")
    gen = SheetGenerator().generate(spec)
    valid_img = load_bytes(gen.pdf_bytes, "valid.pdf", dpi=200)[0].image_bgr
    cv2.imwrite(str(inbox / "valid_sheet.jpg"), valid_img)

    watch_out = tmp_path / "watch_out"
    res_watch = runner.invoke(
        cli_app,
        ["watch", str(inbox), "-o", str(watch_out), "--max-cycles", "1", "--interval", "0.1"],
    )
    assert res_watch.exit_code == 0, res_watch.output
    assert (watch_out / "results.csv").is_file()
    watch_csv = (watch_out / "results.csv").read_text(encoding="utf-8-sig")
    assert "valid_sheet" in watch_csv

    scan_out = tmp_path / "scan_out"
    res_scan = runner.invoke(cli_app, ["scan", str(inbox), "-o", str(scan_out), "--no-overlay"])
    assert res_scan.exit_code == 0, res_scan.output
    scan_json = json.loads((scan_out / "results.json").read_text(encoding="utf-8"))
    assert len(scan_json["sheets"]) == 2
    assert any(s["error"] is not None for s in scan_json["sheets"])
    assert any(s["error"] is None for s in scan_json["sheets"])


def test_roster_csv_size_cap_and_blank_key_sheet_rejection() -> None:
    """Bugs #7 & #10: Enforce roster_csv size caps and reject all-blank teacher key sheets."""
    client = TestClient(create_app())
    spec = get_sheet_preset("quick_quiz_20")

    # Bug #7a: Oversized inline roster_csv form payload (> 512 KB) returns 413
    oversized_inline_csv = "student_id,name\n" + ("100001,Test Student\n" * 35_000)
    res_413 = client.post(
        "/api/generate/roster-packet",
        data={
            "spec_json": json.dumps(spec.model_dump(mode="json")),
            "roster_csv": oversized_inline_csv,
        },
    )
    assert res_413.status_code == 413

    # Bug #7b: Oversized uploaded roster_file (> 2 MB) returns 413
    oversized_file_csv = ("student_id,name\n" + ("100001,Test Student\n" * 120_000)).encode("utf-8")
    res_file_413 = client.post(
        "/api/generate/roster-packet",
        data={"spec_json": json.dumps(spec.model_dump(mode="json"))},
        files={"roster_file": ("huge.csv", oversized_file_csv, "text/csv")},
    )
    assert res_file_413.status_code == 413

    # Bug #10: Blank key sheet raises ValueError / HTTP 400
    gen = SheetGenerator().generate(spec)
    blank = load_bytes(gen.pdf_bytes, "blank.pdf", dpi=200)[0].image_bgr
    blank_sheet, _ = OMRScanner(gen.template).scan_image(blank, source_name="empty_key.jpg")
    with pytest.raises(ValueError, match="No marked answers"):
        extract_answer_key_from_sheets([blank_sheet], template=gen.template)

    ok, encoded = cv2.imencode(".jpg", blank)
    assert ok
    res_400 = client.post(
        "/api/answer-key/from-sheet",
        data={"template_json": "auto"},
        files=[("files", ("empty_key.jpg", encoded.tobytes(), "image/jpeg"))],
    )
    assert res_400.status_code == 400


def test_turkish_exam_50_qr_v3_no_prefill_clears_stale_warning_and_no_dup_student_id() -> None:
    """Bug #9: QR v3 on turkish_exam_50 clears stale TC checksum warning and avoids duplicate STUDENT_ID."""
    tr_spec = get_sheet_preset("turkish_exam_50")
    tr_student = StudentRosterEntry(
        student_id="10000000146",
        name="Çağrı Şahin",  # noqa: RUF001
        classroom="12-A",
        booklet="B",
    )
    tr_pkt = SheetGenerator().generate_roster_packet(tr_spec, [tr_student], pre_fill_id=False)
    tr_img = load_bytes(tr_pkt.pdf_bytes, "tr.pdf", dpi=200)[0].image_bgr
    tr_res, _ = OMRScanner(tr_pkt.template).scan_image(tr_img, source_name="tr.jpg")

    assert tr_res.grouped_values["TC_KIMLIK_NO"] == "10000000146"
    assert tr_res.grouped_values["STUDENT_NAME"] == "Çağrı Şahin"  # noqa: RUF001
    assert "STUDENT_ID" not in tr_res.grouped_values
    assert not any("TC Kimlik" in w for w in tr_res.warnings)
