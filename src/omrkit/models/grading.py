"""Exam grading, scoring policy, and psychometric analytics models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

VerdictType = Literal["correct", "incorrect", "blank", "bonus"]


class SectionRule(BaseModel):
    """Optional section-specific scoring weights (e.g., Math vs Verbal)."""

    name: str
    questions: list[str]
    correct_points: float = 1.0
    incorrect_points: float = 0.0
    blank_points: float = 0.0


class GradingPolicy(BaseModel):
    """Exam scoring rules including negative marking and section weights."""

    name: str = "standard"
    correct_points: float = 1.0
    incorrect_points: float = 0.0
    blank_points: float = 0.0
    partial_credit: bool = False
    bonus_questions: list[str] = Field(default_factory=list)
    sections: list[SectionRule] = Field(default_factory=list)

    @classmethod
    def preset(cls, preset_name: str) -> GradingPolicy:
        """Create a well-known grading policy preset."""
        presets: dict[str, GradingPolicy] = {
            "standard": cls(
                name="standard",
                correct_points=1.0,
                incorrect_points=0.0,
                blank_points=0.0,
            ),
            "yks_tyt": cls(
                name="yks_tyt",
                correct_points=1.0,
                incorrect_points=-0.25,
                blank_points=0.0,
            ),
            "kpss": cls(
                name="kpss",
                correct_points=1.0,
                incorrect_points=-0.25,
                blank_points=0.0,
            ),
            "lgs": cls(
                name="lgs",
                correct_points=1.0,
                incorrect_points=-1.0 / 3.0,
                blank_points=0.0,
            ),
            "sat_legacy": cls(
                name="sat_legacy",
                correct_points=1.0,
                incorrect_points=-0.25,
                blank_points=0.0,
            ),
        }
        if preset_name not in presets:
            available = ", ".join(sorted(presets))
            raise ValueError(f"Unknown grading policy '{preset_name}'. Available: {available}")
        return presets[preset_name]


class AnswerKey(BaseModel):
    """Single- or multi-booklet answer key definition."""

    exam_name: str = "Untitled Exam"
    booklet_field: str | None = None
    default_booklet: str = "A"
    # Mapping booklet_id -> {question_id: expected_answer (str or list of acceptable answers)}
    booklets: dict[str, dict[str, str | list[str]]] = Field(default_factory=dict)
    # Shorthand when only a single answer key is provided without booklets
    answers: dict[str, str | list[str]] = Field(default_factory=dict)

    def resolve_booklet(self, booklet_code: str | None) -> dict[str, str | list[str]]:
        """Resolve question -> expected answer map for the given booklet code."""
        if self.booklets:
            if booklet_code and booklet_code in self.booklets:
                return self.booklets[booklet_code]
            if self.default_booklet in self.booklets:
                return self.booklets[self.default_booklet]
            first_key = next(iter(self.booklets))
            return self.booklets[first_key]
        return self.answers

    def question_ids(self) -> list[str]:
        """Return ordered question IDs from the default booklet."""
        return list(self.resolve_booklet(self.default_booklet).keys())

    @classmethod
    def from_file(cls, path: str | Path) -> AnswerKey:
        """Load an AnswerKey from JSON or YAML."""
        file_path = Path(path)
        raw = file_path.read_text(encoding="utf-8")
        if file_path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
        return cls.model_validate(data)

    def to_file(self, path: str | Path) -> Path:
        """Save an AnswerKey to JSON or YAML."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump(mode="json")
        if file_path.suffix.lower() in {".yaml", ".yml"}:
            file_path.write_text(
                yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
        else:
            file_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        return file_path


class QuestionVerdict(BaseModel):
    """Per-question grading breakdown."""

    question_id: str
    marked: str
    expected: str
    verdict: VerdictType
    points: float
    confidence: float = 1.0


class SectionScore(BaseModel):
    """Per-section subtotal for a student."""

    name: str
    correct: int
    incorrect: int
    blank: int
    score: float
    max_score: float


class StudentGrade(BaseModel):
    """Complete graded scorecard for one optical sheet."""

    sheet_id: str
    source_file: str
    student_metadata: dict[str, str] = Field(default_factory=dict)
    booklet: str = "A"
    total_questions: int = 0
    correct: int = 0
    incorrect: int = 0
    blank: int = 0
    bonus: int = 0
    raw_score: float = 0.0
    max_score: float = 0.0
    percentage: float = 0.0
    flagged_for_review: bool = False
    sections: list[SectionScore] = Field(default_factory=list)
    verdicts: list[QuestionVerdict] = Field(default_factory=list)


class ItemPsychometrics(BaseModel):
    """Classical Test Theory (CTT) statistics for an individual exam question."""

    question_id: str
    expected: str
    attempts: int
    correct_count: int
    incorrect_count: int
    blank_count: int
    difficulty_p: float = Field(ge=0.0, le=1.0)
    discrimination_d: float = Field(ge=-1.0, le=1.0)
    omit_rate: float = Field(ge=0.0, le=1.0)
    option_distribution: dict[str, int] = Field(default_factory=dict)
    quality_flag: Literal["good", "too_easy", "too_hard", "poor_discrimination"] = "good"


class ScoreHistogramBin(BaseModel):
    """Score range bin for distribution visualization."""

    label: str
    low: float
    high: float
    count: int


class ExamAnalytics(BaseModel):
    """Cohort-level statistical and psychometric exam summary."""

    student_count: int
    question_count: int
    mean_score: float
    median_score: float
    std_score: float
    min_score: float
    max_score: float
    mean_percentage: float
    percentiles: dict[str, float] = Field(default_factory=dict)
    kr20_reliability: float | None = None
    histogram: list[ScoreHistogramBin] = Field(default_factory=list)
    items: list[ItemPsychometrics] = Field(default_factory=list)


class GradingReport(BaseModel):
    """Combined grading results and psychometric analytics for an exam batch."""

    exam_name: str
    policy_name: str
    grades: list[StudentGrade] = Field(default_factory=list)
    analytics: ExamAnalytics
