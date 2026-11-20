"""CSV, JSON, formatted Excel (.xlsx), and PDF student scorecard exporters."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

from omrkit.models.grading import GradingReport, StudentGrade
from omrkit.models.scan import SheetResult


def _collect_columns(sheets: list[SheetResult]) -> tuple[list[str], list[str]]:
    grouped_cols: list[str] = []
    field_cols: list[str] = []
    grouped_field_prefixes: set[str] = set()

    for s in sheets:
        for gk in s.grouped_values:
            if gk not in grouped_cols:
                grouped_cols.append(gk)
                grouped_field_prefixes.add(gk.lower() + "_")
        for fk in s.fields:
            if fk not in field_cols:
                field_cols.append(fk)

    # Keep ungrouped fields cleanly in output
    filtered_fields = [
        fk
        for fk in field_cols
        if not any(fk.lower().startswith(pref) for pref in grouped_field_prefixes)
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
        *grouped_cols,
    ]
    if report:
        headers.extend(["score", "max_score", "percentage", "correct", "incorrect", "blank"])
    headers.extend(field_cols)

    writer = csv.writer(buf)
    writer.writerow(headers)

    for s in sheets:
        row: list[object] = [
            s.sheet_id,
            s.source_file,
            s.page_index,
            f"{s.overall_confidence:.4f}",
            len(s.review_items),
            *[s.grouped_values.get(gk, "") for gk in grouped_cols],
        ]
        if report:
            g = grade_by_id.get(s.sheet_id)
            if g:
                row.extend(
                    [g.raw_score, g.max_score, g.percentage, g.correct, g.incorrect, g.blank]
                )
            else:
                row.extend(["", "", "", "", "", ""])
        row.extend(s.fields[fk].value if fk in s.fields else "" for fk in field_cols)
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

    headers = ["Sheet ID", "Source File", "Confidence", "Review Flags", *grouped_cols]
    if report:
        headers.extend(["Score", "Max Score", "Percent (%)", "Correct", "Incorrect", "Blank"])
    headers.extend(field_cols)
    ws_resp.append(headers)

    for cell in ws_resp[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    for row_idx, s in enumerate(sheets, start=2):
        row: list[object] = [
            s.sheet_id,
            s.source_file,
            round(s.overall_confidence, 4),
            len(s.review_items),
            *[s.grouped_values.get(gk, "") for gk in grouped_cols],
        ]
        if report:
            g = grade_by_id.get(s.sheet_id)
            if g:
                row.extend(
                    [g.raw_score, g.max_score, g.percentage, g.correct, g.incorrect, g.blank]
                )
            else:
                row.extend(["", "", "", "", "", ""])
        row.extend(s.fields[fk].value if fk in s.fields else "" for fk in field_cols)
        ws_resp.append(row)
        if s.review_items:
            ws_resp.cell(row=row_idx, column=4).fill = warn_fill

    ws_resp.freeze_panes = "A2"

    # Sheet 2 & 3: Summary & Item Psychometrics when graded
    if report is not None:
        ws_sum = wb.create_sheet("Exam Summary")
        a = report.analytics
        summary_rows = [
            ("Exam Name", report.exam_name),
            ("Grading Policy", report.policy_name),
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
                    item.question_id,
                    item.expected,
                    item.correct_count,
                    item.incorrect_count,
                    item.blank_count,
                    item.difficulty_p,
                    item.discrimination_d,
                    item.omit_rate,
                    item.quality_flag,
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


def export_pdf_scorecard_bytes(grade: StudentGrade, exam_name: str = "Exam Scorecard") -> bytes:
    """Render a clean, printable A4 PDF student scorecard in memory."""
    buf = io.BytesIO()
    w, h = A4
    pdf = rl_canvas.Canvas(buf, pagesize=A4)
    pdf.setTitle(f"Scorecard - {grade.sheet_id}")

    def safe(text: str) -> str:
        return text.translate(str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU"))

    ink = colors.HexColor("#14181F")
    muted = colors.HexColor("#5C6773")
    green = colors.HexColor("#0F8A5F")
    red = colors.HexColor("#DC2626")
    border = colors.HexColor("#D5DCE4")

    # Header
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(42, h - 52, safe(exam_name))
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(42, h - 68, f"Sheet: {safe(grade.sheet_id)}  |  Booklet: {grade.booklet}")

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
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(x + 10, y_card + 33, label)
        pdf.setFillColor(clr)
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(x + 10, y_card + 13, val)

    # Metadata row
    y_cursor = y_card - 22
    if grade.student_metadata:
        meta_text = "   |   ".join(f"{k}: {v or '-'}" for k, v in grade.student_metadata.items())
        pdf.setFillColor(ink)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(42, y_cursor, safe(meta_text))
        y_cursor -= 20

    # Question verdict grid (4 columns)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(42, y_cursor, "Question Breakdown")
    y_cursor -= 16

    cols = 4
    col_w = (w - 84) / cols
    row_h = 14
    rows_per_col = max(1, (len(grade.verdicts) + cols - 1) // cols)

    for idx, v in enumerate(grade.verdicts):
        col = idx // rows_per_col
        row = idx % rows_per_col
        x = 42 + col * col_w
        y = y_cursor - row * row_h
        if y < 48:
            break
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.setFillColor(ink)
        pdf.drawString(x, y, f"{v.question_id}:")
        pdf.setFont("Helvetica", 7.5)
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

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(42, 28, "Generated by OMRKit v2.0 — https://github.com/duhanguler/omr")
    pdf.showPage()
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
