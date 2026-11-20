"""OMRKit — Modern Optical Mark Recognition SDK, Sheet Generator & Exam Psychometrics."""

from omrkit.core.benchmark import BenchmarkScenarioResult, run_benchmark
from omrkit.core.scanner import OMRScanner
from omrkit.core.validators import validate_luhn, validate_tr_tckn
from omrkit.generator.pdf_sheet import GeneratedSheet, SheetGenerator
from omrkit.generator.presets import IdGridSpec, SheetSpec, get_sheet_preset, get_sheet_presets
from omrkit.grading.analytics import compute_exam_analytics
from omrkit.grading.grader import ExamGrader
from omrkit.io.exporters import export_csv, export_excel, export_json, export_pdf_scorecard
from omrkit.models import (
    AnswerKey,
    BatchResult,
    DetectionConfig,
    ExamAnalytics,
    FieldBlock,
    FieldReading,
    GradingPolicy,
    GradingReport,
    RegistrationConfig,
    ReviewItem,
    SheetResult,
    StudentGrade,
    Template,
)

__version__ = "2.0.0"

__all__ = [
    "AnswerKey",
    "BatchResult",
    "BenchmarkScenarioResult",
    "DetectionConfig",
    "ExamAnalytics",
    "ExamGrader",
    "FieldBlock",
    "FieldReading",
    "GeneratedSheet",
    "GradingPolicy",
    "GradingReport",
    "IdGridSpec",
    "OMRScanner",
    "RegistrationConfig",
    "ReviewItem",
    "SheetGenerator",
    "SheetResult",
    "SheetSpec",
    "StudentGrade",
    "Template",
    "__version__",
    "compute_exam_analytics",
    "export_csv",
    "export_excel",
    "export_json",
    "export_pdf_scorecard",
    "get_sheet_preset",
    "get_sheet_presets",
    "run_benchmark",
    "validate_luhn",
    "validate_tr_tckn",
]
