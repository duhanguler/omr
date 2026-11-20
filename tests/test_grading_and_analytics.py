"""Tests for ExamGrader policies, CTT psychometrics, and CSV/Excel/PDF exports."""

from __future__ import annotations

import io
from pathlib import Path

from openpyxl import load_workbook

from omrkit.grading import ExamGrader
from omrkit.io.exporters import (
    export_csv,
    export_excel,
    export_json,
    export_pdf_scorecard_bytes,
)
from omrkit.io.loader import load_bytes
from omrkit.models import (
    AnswerKey,
    FieldReading,
    GradingPolicy,
    SectionRule,
    SheetResult,
)


def _make_sheet(sheet_id: str, answers: dict[str, str], booklet: str = "A") -> SheetResult:
    fields = {
        qid: FieldReading(
            field_id=qid,
            block_name="MCQ",
            value=val,
            selected_options=list(val) if val else [],
            confidence=0.98,
            status="blank" if val == "" else "ok",
        )
        for qid, val in answers.items()
    }
    fields["BOOKLET"] = FieldReading(
        field_id="BOOKLET",
        block_name="BOOKLET",
        value=booklet,
        selected_options=[booklet],
        confidence=0.99,
        status="ok",
    )
    return SheetResult(
        sheet_id=sheet_id,
        source_file=f"{sheet_id}.jpg",
        template_name="test_exam",
        fields=fields,
        grouped_values={"STUDENT_ID": sheet_id},
    )


def test_yks_negative_marking_booklets_bonus_and_sections() -> None:
    key = AnswerKey(
        exam_name="YKS Mock",
        booklet_field="BOOKLET",
        default_booklet="A",
        booklets={
            "A": {"q1": "A", "q2": "B", "q3": "C", "q4": "D", "q5": "E", "q6": "A"},
            "B": {"q1": "B", "q2": "C", "q3": "D", "q4": "E", "q5": "A", "q6": "B"},
        },
    )
    policy = GradingPolicy(
        name="yks_custom",
        correct_points=1.0,
        incorrect_points=-0.25,
        blank_points=0.0,
        bonus_questions=["q6"],
        sections=[
            SectionRule(
                name="Math", questions=["q1..3"], correct_points=1.0, incorrect_points=-0.25
            ),
            SectionRule(
                name="Science", questions=["q4..6"], correct_points=1.0, incorrect_points=-0.25
            ),
        ],
    )
    grader = ExamGrader(key, policy)

    # Booklet A: q1=A (ok), q2=A (wrong -0.25), q3=C (ok), q4="" (blank), q5=E (ok), q6=B (bonus +1)
    s1 = _make_sheet(
        "s1", {"q1": "A", "q2": "A", "q3": "C", "q4": "", "q5": "E", "q6": "B"}, booklet="A"
    )
    # Booklet B: all correct
    s2 = _make_sheet(
        "s2", {"q1": "B", "q2": "C", "q3": "D", "q4": "E", "q5": "A", "q6": "B"}, booklet="B"
    )

    g1 = grader.grade_sheet(s1)
    assert g1.correct == 3
    assert g1.incorrect == 1
    assert g1.blank == 1
    assert g1.bonus == 1
    assert g1.raw_score == 3.75  # 3 + 1 bonus - 0.25
    assert len(g1.sections) == 2

    g2 = grader.grade_sheet(s2)
    assert g2.raw_score == 6.0
    assert g2.percentage == 100.0


def test_psychometrics_and_all_exporters(tmp_path: Path) -> None:
    key = AnswerKey(
        exam_name="CTT Validation Exam",
        answers={"q1": "A", "q2": "B", "q3": "C", "q4": "D", "q5": "E"},
    )
    cohort = [
        _make_sheet("st1", {"q1": "A", "q2": "B", "q3": "C", "q4": "D", "q5": "E"}),
        _make_sheet("st2", {"q1": "A", "q2": "B", "q3": "C", "q4": "D", "q5": "A"}),
        _make_sheet("st3", {"q1": "A", "q2": "B", "q3": "A", "q4": "", "q5": "A"}),
        _make_sheet("st4", {"q1": "A", "q2": "A", "q3": "A", "q4": "A", "q5": "A"}),
        _make_sheet("st5", {"q1": "B", "q2": "A", "q3": "A", "q4": "B", "q5": "B"}),
    ]
    report = ExamGrader(key, GradingPolicy.preset("standard")).grade_batch(cohort)

    a = report.analytics
    assert a.student_count == 5
    assert a.question_count == 5
    assert a.max_score == 5.0
    assert a.min_score == 0.0
    assert a.kr20_reliability is not None
    assert len(a.items) == 5
    assert len(a.histogram) == 10

    csv_path = export_csv(cohort, tmp_path / "out.csv", report=report)
    json_path = export_json(cohort, tmp_path / "out.json", report=report)
    xlsx_path = export_excel(cohort, tmp_path / "out.xlsx", report=report)

    assert csv_path.exists() and "st1" in csv_path.read_text(encoding="utf-8-sig")
    assert json_path.exists()
    wb = load_workbook(io.BytesIO(xlsx_path.read_bytes()))
    assert set(wb.sheetnames) == {"Responses", "Exam Summary", "Item Analytics"}

    pdf_bytes = export_pdf_scorecard_bytes(report.grades[0], exam_name=report.exam_name)
    assert pdf_bytes.startswith(b"%PDF")
    pages = load_bytes(pdf_bytes, "scorecard.pdf", dpi=100)
    assert len(pages) == 1
