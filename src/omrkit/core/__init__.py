"""Core scanning, auto-detection, migration, validation, and benchmarking engines."""

from omrkit.core.auto_scanner import (
    resolve_template_for_image,
    scan_bytes_auto,
    scan_file_auto,
    scan_image_auto,
    scan_page_auto,
)
from omrkit.core.benchmark import (
    BenchmarkScenarioResult,
    apply_camera_distortion,
    render_synthetic_filled_sheet,
    run_benchmark,
)
from omrkit.core.migrator import migrate_legacy_template_dict, migrate_legacy_template_file
from omrkit.core.scanner import OMRScanner
from omrkit.core.validators import (
    run_validator,
    validate_digits,
    validate_luhn,
    validate_non_empty,
    validate_tr_tckn,
)

__all__ = [
    "BenchmarkScenarioResult",
    "OMRScanner",
    "apply_camera_distortion",
    "migrate_legacy_template_dict",
    "migrate_legacy_template_file",
    "render_synthetic_filled_sheet",
    "resolve_template_for_image",
    "run_benchmark",
    "run_validator",
    "scan_bytes_auto",
    "scan_file_auto",
    "scan_image_auto",
    "scan_page_auto",
    "validate_digits",
    "validate_luhn",
    "validate_non_empty",
    "validate_tr_tckn",
]
