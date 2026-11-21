"""OMRKit — Modern Optical Mark Recognition SDK, Sheet Generator & Exam Psychometrics."""

from omrkit._version import __version__
from omrkit.core.auto_scanner import (
    resolve_template_for_image,
    resolve_template_payload_for_image,
    scan_file_auto,
    scan_image_auto,
)
from omrkit.core.benchmark import BenchmarkScenarioResult, run_benchmark
from omrkit.core.migrator import migrate_legacy_template_dict, migrate_legacy_template_file
from omrkit.core.scanner import OMRScanner
from omrkit.core.validators import validate_luhn, validate_tr_tckn
from omrkit.generator.pdf_sheet import GeneratedSheet, SheetGenerator
from omrkit.generator.presets import IdGridSpec, SheetSpec, get_sheet_preset, get_sheet_presets
from omrkit.generator.roster import StudentRosterEntry, parse_roster_csv, parse_roster_file
from omrkit.grading.analytics import compute_exam_analytics
from omrkit.grading.grader import ExamGrader
from omrkit.grading.key_extractor import ExtractedKeyResult, extract_answer_key_from_sheets
from omrkit.io.exporters import (
    export_canvas_csv,
    export_csv,
    export_excel,
    export_json,
    export_merged_scorecards_pdf,
    export_moodle_csv,
    export_pdf_scorecard,
)
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
from omrkit.vision.qr import SheetQRPayload, detect_sheet_qr, detect_sheet_qr_payload

__all__ = [
    "AnswerKey",
    "BatchResult",
    "BenchmarkScenarioResult",
    "DetectionConfig",
    "ExamAnalytics",
    "ExamGrader",
    "ExtractedKeyResult",
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
    "SheetQRPayload",
    "SheetResult",
    "SheetSpec",
    "StudentGrade",
    "StudentRosterEntry",
    "Template",
    "__version__",
    "compute_exam_analytics",
    "detect_layout_from_blank",
    "detect_sheet_qr",
    "detect_sheet_qr_payload",
    "export_canvas_csv",
    "export_csv",
    "export_excel",
    "export_json",
    "export_merged_scorecards_pdf",
    "export_moodle_csv",
    "export_pdf_scorecard",
    "extract_answer_key_from_sheets",
    "get_sheet_preset",
    "get_sheet_presets",
    "migrate_legacy_template_dict",
    "migrate_legacy_template_file",
    "parse_roster_csv",
    "parse_roster_file",
    "resolve_template_for_image",
    "resolve_template_payload_for_image",
    "run_benchmark",
    "scan_file_auto",
    "scan_image_auto",
    "validate_luhn",
    "validate_tr_tckn",
]
