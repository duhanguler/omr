"""Core scanning, validation, and benchmarking engines."""

from omrkit.core.benchmark import (
    BenchmarkScenarioResult,
    apply_camera_distortion,
    render_synthetic_filled_sheet,
    run_benchmark,
)
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
    "render_synthetic_filled_sheet",
    "run_benchmark",
    "run_validator",
    "validate_digits",
    "validate_luhn",
    "validate_non_empty",
    "validate_tr_tckn",
]
