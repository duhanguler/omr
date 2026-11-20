"""OMRKit — Modern Optical Mark Recognition SDK, Sheet Generator & Exam Psychometrics."""

from omrkit.core.auto_scanner import (
    resolve_template_for_image,
    scan_file_auto,
    scan_image_auto,
)
from omrkit.core.benchmark import BenchmarkScenarioResult, run_benchmark
from omrkit.core.migrator import migrate_legacy_template_dict, migrate_legacy_template_file
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
from omrkit.vision.grid_finder import detect_layout_from_blank
from omrkit.vision.qr import detect_sheet_qr

__version__ = "2.1.0"

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
    "detect_layout_from_blank",
    "detect_sheet_qr",
    "export_csv",
    "export_excel",
    "export_json",
    "export_pdf_scorecard",
    "get_sheet_preset",
    "get_sheet_presets",
    "migrate_legacy_template_dict",
    "migrate_legacy_template_file",
    "resolve_template_for_image",
    "run_benchmark",
    "scan_file_auto",
    "scan_image_auto",
    "validate_luhn",
    "validate_tr_tckn",
]
