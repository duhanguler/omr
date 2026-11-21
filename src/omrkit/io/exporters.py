"""CSV, JSON, formatted Excel (.xlsx), and PDF student scorecard exporters."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

from omrkit._version import __version__
from omrkit.io.pdf_fonts import PdfFontPair, get_pdf_fonts
from omrkit.models.grading import GradingReport, StudentGrade
from omrkit.models.scan import SheetResult

_ILLEGAL_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_spreadsheet_text(value: str, *, allow_numeric_sign: bool = False) -> str:
    """Strip Excel/XML-illegal control characters and neutralize spreadsheet formula injection."""
    cleaned = _ILLEGAL_XML_CHARS_RE.sub("", value)
    if not cleaned:
        return ""
    if cleaned[0] in _FORMULA_PREFIXES:
        if allow_numeric_sign and cleaned[0] in {"+", "-"}:
            try:
                float(cleaned)
                return cleaned
            except ValueError:
                pass
        return f"'{cleaned}"
    return cleaned


def _collect_columns(sheets: list[SheetResult]) -> tuple[list[str], list[str]]:
    grouped_cols: list[str] = []
    grouped_lower: set[str] = set()
    field_cols: list[str] = []
    grouped_field_prefixes: set[str] = set()

    for s in sheets:
        for gk in s.grouped_values:
            if gk not in grouped_cols:
                grouped_cols.append(gk)
                grouped_lower.add(gk.lower())
                grouped_field_prefixes.add(gk.lower() + "_")
        for fk in s.fields:
            if fk not in field_cols:
                field_cols.append(fk)

    # Keep ungrouped fields cleanly in output without duplicating grouped/exact columns
    filtered_fields = [
        fk
        for fk in field_cols
        if fk.lower() not in grouped_lower
        and not any(fk.lower().startswith(pref) for pref in grouped_field_prefixes)
    ]
    return grouped_cols, filtered_fields


def export_csv_string(
    sheets: list[SheetResult],
    report: GradingReport | None = None,
) -> str:
    """Serialize scan results (and optional grades) to a clean CSV string."""
    buf = io.StringIO()
    grouped_cols, field_cols = _collect_columns(sheets)
    grade_by_id = {g.sheet_id: g for g in report.grades} if report else {}

    headers = [
        "sheet_id",
        "source_file",
        "page_index",
        "overall_confidence",
        "review_flags",
        *[_sanitize_spreadsheet_text(gk) for gk in grouped_cols],
    ]
    if report:
        headers.extend(["score", "max_score", "percentage", "correct", "incorrect", "blank"])
    headers.extend(_sanitize_spreadsheet_text(fk) for fk in field_cols)

    writer = csv.writer(buf)
    writer.writerow(headers)

    for s in sheets:
        row: list[object] = [
            _sanitize_spreadsheet_text(s.sheet_id),
            _sanitize_spreadsheet_text(s.source_file),
            s.page_index,
            f"{s.overall_confidence:.4f}",
            len(s.review_items),
            *[_sanitize_spreadsheet_text(s.grouped_values.get(gk, "")) for gk in grouped_cols],
        ]
        if report:
            g = grade_by_id.get(s.sheet_id)
            if g:
                row.extend(
                    [g.raw_score, g.max_score, g.percentage, g.correct, g.incorrect, g.blank]
                )
            else:
                row.extend(["", "", "", "", "", ""])
        row.extend(
            _sanitize_spreadsheet_text(s.fields[fk].value) if fk in s.fields else ""
            for fk in field_cols
        )
        writer.writerow(row)

    return buf.getvalue()


def export_csv(
    sheets: list[SheetResult],
    path: str | Path,
    report: GradingReport | None = None,
) -> Path:
    """Write scan and optional grading results to a CSV file."""
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(export_csv_string(sheets, report=report), encoding="utf-8-sig")
    return dst


def export_json(
    sheets: list[SheetResult],
    path: str | Path,
    report: GradingReport | None = None,
) -> Path:
    """Write structured scan results and optional grading report to JSON."""
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "sheets": [s.model_dump(mode="json") for s in sheets],
    }
    if report is not None:
        payload["grading_report"] = report.model_dump(mode="json")
    dst.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dst


def export_excel_bytes(
    sheets: list[SheetResult],
    report: GradingReport | None = None,
) -> bytes:
    """Build a multi-sheet formatted Excel (.xlsx) workbook in memory."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError as exc:
        raise RuntimeError(
            "Excel export requires 'openpyxl'. Install with: pip install 'omrkit[excel]'"
        ) from exc

    wb = Workbook()
    header_fill = PatternFill(start_color="18202A", end_color="18202A", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    warn_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

    # Sheet 1: Responses
    ws_resp = wb.active
    assert ws_resp is not None
    ws_resp.title = "Responses"

    grouped_cols, field_cols = _collect_columns(sheets)
    grade_by_id = {g.sheet_id: g for g in report.grades} if report else {}

    headers = [
        "Sheet ID",
        "Source File",
        "Confidence",
        "Review Flags",
        *[_sanitize_spreadsheet_text(gk) for gk in grouped_cols],
    ]
    if report:
        headers.extend(["Score", "Max Score", "Percent (%)", "Correct", "Incorrect", "Blank"])
    headers.extend(_sanitize_spreadsheet_text(fk) for fk in field_cols)
    ws_resp.append(headers)

    for cell in ws_resp[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for row_idx, s in enumerate(sheets, start=2):
        row: list[object] = [
            _sanitize_spreadsheet_text(s.sheet_id),
            _sanitize_spreadsheet_text(s.source_file),
            round(s.overall_confidence, 4),
            len(s.review_items),
            *[_sanitize_spreadsheet_text(s.grouped_values.get(gk, "")) for gk in grouped_cols],
        ]
        if report:
            g = grade_by_id.get(s.sheet_id)
            if g:
                row.extend(
                    [g.raw_score, g.max_score, g.percentage, g.correct, g.incorrect, g.blank]
                )
            else:
                row.extend(["", "", "", "", "", ""])
        row.extend(
            _sanitize_spreadsheet_text(s.fields[fk].value) if fk in s.fields else ""
            for fk in field_cols
        )
        ws_resp.append(row)
        if s.review_items:
            ws_resp.cell(row=row_idx, column=4).fill = warn_fill

    ws_resp.freeze_panes = "A2"

    # Sheet 2 & 3: Summary & Item Psychometrics when graded
    if report is not None:
        ws_sum = wb.create_sheet("Exam Summary")
        a = report.analytics
        summary_rows = [
            ("Exam Name", _sanitize_spreadsheet_text(report.exam_name)),
            ("Grading Policy", _sanitize_spreadsheet_text(report.policy_name)),
            ("Students Graded", a.student_count),
            ("Questions", a.question_count),
            ("Mean Score", a.mean_score),
            ("Median Score", a.median_score),
            ("Std Dev", a.std_score),
            ("Min Score", a.min_score),
            ("Max Score", a.max_score),
            ("Mean Percentage (%)", a.mean_percentage),
            ("KR-20 Reliability", a.kr20_reliability if a.kr20_reliability is not None else "N/A"),
        ]
        ws_sum.append(["Metric", "Value"])
        for cell in ws_sum[1]:
            cell.fill = header_fill
            cell.font = header_font
        for metric, val in summary_rows:
            ws_sum.append([metric, val])

        ws_items = wb.create_sheet("Item Analytics")
        item_headers = [
            "Question",
            "Expected",
            "Correct",
            "Incorrect",
            "Blank",
            "Difficulty (p)",
            "Discrimination (D)",
            "Omit Rate",
            "Quality Flag",
        ]
        ws_items.append(item_headers)
        for cell in ws_items[1]:
            cell.fill = header_fill
            cell.font = header_font
        for item in a.items:
            ws_items.append(
                [
                    _sanitize_spreadsheet_text(item.question_id),
                    _sanitize_spreadsheet_text(item.expected),
                    item.correct_count,
                    item.incorrect_count,
                    item.blank_count,
                    item.difficulty_p,
                    item.discrimination_d,
                    item.omit_rate,
                    _sanitize_spreadsheet_text(item.quality_flag),
                ]
            )
        ws_items.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_excel(
    sheets: list[SheetResult],
    path: str | Path,
    report: GradingReport | None = None,
) -> Path:
    """Write formatted Excel report to disk."""
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(export_excel_bytes(sheets, report=report))
    return dst


def _render_scorecard_pages(
    pdf: rl_canvas.Canvas,
    grade: StudentGrade,
    exam_name: str,
    fonts: PdfFontPair,
) -> None:
    """Draw one student's A4 scorecard page(s) onto an existing ReportLab canvas."""
    w, h = A4
    ink = colors.HexColor("#14181F")
    muted = colors.HexColor("#5C6773")
    green = colors.HexColor("#0F8A5F")
    red = colors.HexColor("#DC2626")
    border = colors.HexColor("#D5DCE4")

    # Header
    pdf.setFillColor(ink)
    pdf.setFont(fonts.bold, 15.5)
    pdf.drawString(42, h - 52, fonts.format_text(exam_name))
    pdf.setFillColor(muted)
    pdf.setFont(fonts.regular, 9)
    student_label = grade.student_metadata.get("STUDENT_NAME", "").strip()
    header_sub = f"Sheet: {grade.sheet_id}  |  Booklet: {grade.booklet}"
    if student_label:
        header_sub = f"Student: {student_label}  |  {header_sub}"
    pdf.drawString(42, h - 68, fonts.format_text(header_sub))

    # Summary KPI cards
    y_card = h - 132
    card_w = (w - 84 - 24) / 4.0
    kpis = [
        ("SCORE", f"{grade.raw_score:.2f} / {grade.max_score:.2f}", ink),
        ("PERCENTAGE", f"{grade.percentage:.1f}%", green if grade.percentage >= 50 else red),
        ("CORRECT", str(grade.correct), green),
        ("WRONG / BLANK", f"{grade.incorrect} / {grade.blank}", red if grade.incorrect else muted),
    ]
    for idx, (label, val, clr) in enumerate(kpis):
        x = 42 + idx * (card_w + 8)
        pdf.setStrokeColor(border)
        pdf.setFillColor(colors.HexColor("#FAF9F6"))
        pdf.roundRect(x, y_card, card_w, 48, 4, stroke=1, fill=1)
        pdf.setFillColor(muted)
        pdf.setFont(fonts.bold, 7)
        pdf.drawString(x + 10, y_card + 33, label)
        pdf.setFillColor(clr)
        pdf.setFont(fonts.bold, 13)
        pdf.drawString(x + 10, y_card + 13, val)

    # Metadata row
    y_cursor = y_card - 22
    if grade.student_metadata:
        meta_text = "   |   ".join(f"{k}: {v or '-'}" for k, v in grade.student_metadata.items())
        pdf.setFillColor(ink)
        pdf.setFont(fonts.regular, 9)
        pdf.drawString(42, y_cursor, fonts.format_text(meta_text))
        y_cursor -= 20

    # Question verdict grid (4 columns, auto-paginating for very large exams)
    pdf.setFillColor(ink)
    pdf.setFont(fonts.bold, 10)
    pdf.drawString(42, y_cursor, "Question Breakdown")
    y_cursor -= 16

    cols = 4
    col_w = (w - 84) / cols
    row_h = 14
    max_rows_first_page = max(1, int((y_cursor - 52) // row_h))
    max_rows_next_page = max(1, int((h - 96) // row_h))
    page_capacity = max_rows_first_page * cols

    verdicts = grade.verdicts
    offset = 0
    page_num = 1
    while offset < len(verdicts) or (offset == 0 and not verdicts):
        if page_num > 1:
            pdf.setFillColor(muted)
            pdf.setFont(fonts.regular, 7)
            pdf.drawString(42, 28, f"Generated by OMRKit v{__version__} — Page {page_num - 1}")
            pdf.showPage()
            y_cursor = h - 52
            pdf.setFillColor(ink)
            pdf.setFont(fonts.bold, 10)
            pdf.drawString(
                42, y_cursor, fonts.format_text(f"{exam_name} — Question Breakdown (cont.)")
            )
            y_cursor -= 18
            page_capacity = max_rows_next_page * cols

        chunk = verdicts[offset : offset + page_capacity]
        rows_per_col = max(1, (len(chunk) + cols - 1) // cols)
        for idx, v in enumerate(chunk):
            col = idx // rows_per_col
            row = idx % rows_per_col
            x = 42 + col * col_w
            y = y_cursor - row * row_h
            pdf.setFont(fonts.bold, 7.5)
            pdf.setFillColor(ink)
            pdf.drawString(x, y, f"{v.question_id}:")
            pdf.setFont(fonts.regular, 7.5)
            mark_str = v.marked or "-"
            if v.verdict in {"correct", "bonus"}:
                pdf.setFillColor(green)
                tag = "OK"
            elif v.verdict == "blank":
                pdf.setFillColor(muted)
                tag = "--"
            else:
                pdf.setFillColor(red)
                tag = "X"
            pdf.drawString(x + 28, y, f"{mark_str} (Key: {v.expected}) [{tag}]")

        offset += len(chunk)
        if not verdicts:
            break
        page_num += 1

    pdf.setFillColor(muted)
    pdf.setFont(fonts.regular, 7)
    pdf.drawString(
        42, 28, f"Generated by OMRKit v{__version__} — https://github.com/duhanguler/omr"
    )
    pdf.showPage()


def export_pdf_scorecard_bytes(grade: StudentGrade, exam_name: str = "Exam Scorecard") -> bytes:
    """Render a clean, printable A4 PDF student scorecard in memory."""
    fonts = get_pdf_fonts()
    buf = io.BytesIO()
    pdf = rl_canvas.Canvas(buf, pagesize=A4)
    pdf.setTitle(fonts.format_text(f"Scorecard - {grade.sheet_id}"))
    _render_scorecard_pages(pdf, grade, exam_name, fonts)
    pdf.save()
    return buf.getvalue()


def export_pdf_scorecard(
    grade: StudentGrade,
    path: str | Path,
    exam_name: str = "Exam Scorecard",
) -> Path:
    """Write a student PDF scorecard to disk."""
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(export_pdf_scorecard_bytes(grade, exam_name=exam_name))
    return dst


def export_merged_scorecards_pdf_bytes(report: GradingReport) -> bytes:
    """Render a single printable multi-page PDF containing every student's scorecard."""
    if not report.grades:
        raise ValueError("Cannot export merged scorecards: grading report has no graded sheets.")
    fonts = get_pdf_fonts()
    buf = io.BytesIO()
    pdf = rl_canvas.Canvas(buf, pagesize=A4)
    pdf.setTitle(fonts.format_text(f"{report.exam_name} — Class Scorecards"))
    pdf.setAuthor(f"OMRKit v{__version__}")
    for grade in report.grades:
        _render_scorecard_pages(pdf, grade, report.exam_name, fonts)
    pdf.save()
    return buf.getvalue()


def export_merged_scorecards_pdf(report: GradingReport, path: str | Path) -> Path:
    """Write a merged multi-page class scorecards PDF to disk."""
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(export_merged_scorecards_pdf_bytes(report))
    return dst


def export_scorecards_zip_bytes(report: GradingReport) -> bytes:
    """Bundle individual per-student PDF scorecards into a single ZIP archive in memory."""
    if not report.grades:
        raise ValueError("Cannot export scorecards ZIP: grading report has no graded sheets.")
    buf = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, grade in enumerate(report.grades, start=1):
            raw_stem = (
                re.sub(r"[^A-Za-z0-9._-]+", "_", grade.sheet_id).strip("._-") or f"student_{idx}"
            )
            fname = f"{raw_stem}_scorecard.pdf"
            if fname in used_names:
                fname = f"{raw_stem}_{idx}_scorecard.pdf"
            used_names.add(fname)
            zf.writestr(fname, export_pdf_scorecard_bytes(grade, exam_name=report.exam_name))
    return buf.getvalue()


def _resolve_lms_identity(grade: StudentGrade) -> tuple[str, str, str, str]:
    """Resolve (student_id, full_name, classroom, email) from StudentGrade metadata."""
    meta = grade.student_metadata
    sid = (
        meta.get("STUDENT_ID")
        or meta.get("OGRENCI_NO")
        or meta.get("TC_KIMLIK_NO")
        or grade.sheet_id
    ).strip()
    name = (meta.get("STUDENT_NAME") or grade.sheet_id).strip()
    classroom = (meta.get("CLASSROOM") or "").strip()
    email = (meta.get("EMAIL") or "").strip()
    return sid, name, classroom, email


def export_moodle_csv_string(report: GradingReport) -> str:
    """Export grades in Moodle Offline Grading / Gradebook import CSV format."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Identifier",
            "Full name",
            "ID number",
            "Email address",
            "Grade",
            "Maximum Grade",
            "Feedback comments",
        ]
    )
    for grade in report.grades:
        sid, name, classroom, email = _resolve_lms_identity(grade)
        class_suffix = f" | Class {classroom}" if classroom else ""
        feedback = (
            f"Booklet {grade.booklet}{class_suffix} | "
            f"{grade.correct}/{grade.total_questions} correct, "
            f"{grade.incorrect} wrong, {grade.blank} blank ({grade.percentage:.1f}%)"
        )
        writer.writerow(
            [
                _sanitize_spreadsheet_text(f"Participant {sid}"),
                _sanitize_spreadsheet_text(name),
                _sanitize_spreadsheet_text(sid),
                _sanitize_spreadsheet_text(email),
                f"{grade.raw_score:.2f}",
                f"{grade.max_score:.2f}",
                _sanitize_spreadsheet_text(feedback),
            ]
        )
    return buf.getvalue()


def export_moodle_csv(report: GradingReport, path: str | Path) -> Path:
    """Write a Moodle Gradebook import CSV (UTF-8 with BOM) to disk."""
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(export_moodle_csv_string(report), encoding="utf-8-sig")
    return dst


def export_canvas_csv_string(report: GradingReport, assignment_name: str | None = None) -> str:
    """Export grades in Canvas LMS Gradebook import CSV format (including Points Possible row)."""
    col_name = _sanitize_spreadsheet_text(
        (assignment_name or report.exam_name or "OMRKit Exam").strip()
    )
    max_possible = report.grades[0].max_score if report.grades else 100.0

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Student", "ID", "SIS User ID", "SIS Login ID", "Section", col_name])
    writer.writerow(["    Points Possible", "", "", "", "", f"{max_possible:.2f}"])
    for grade in report.grades:
        sid, name, classroom, email = _resolve_lms_identity(grade)
        writer.writerow(
            [
                _sanitize_spreadsheet_text(name),
                _sanitize_spreadsheet_text(sid),
                _sanitize_spreadsheet_text(sid),
                _sanitize_spreadsheet_text(email or sid),
                _sanitize_spreadsheet_text(classroom),
                f"{grade.raw_score:.2f}",
            ]
        )
    return buf.getvalue()


def export_canvas_csv(
    report: GradingReport,
    path: str | Path,
    assignment_name: str | None = None,
) -> Path:
    """Write a Canvas LMS Gradebook import CSV (UTF-8 with BOM) to disk."""
    dst = Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        export_canvas_csv_string(report, assignment_name=assignment_name),
        encoding="utf-8-sig",
    )
    return dst
