"""Environment-driven API configuration and public demo abuse-protection limits."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_positive_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        val = int(raw.strip())
        return val if val > 0 else default
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class APISettings:
    """Runtime guardrails for the FastAPI REST API and hosted Web Studio demos."""

    demo_mode: bool = False
    max_upload_mb: int = 15
    max_files_per_scan: int = 20
    max_pdf_pages: int = 25

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def limits_dict(self) -> dict[str, int]:
        return {
            "max_upload_mb": self.max_upload_mb,
            "max_files_per_scan": self.max_files_per_scan,
            "max_pdf_pages": self.max_pdf_pages,
        }


def get_api_settings() -> APISettings:
    """Read current API settings from environment variables."""
    return APISettings(
        demo_mode=_parse_bool(os.environ.get("OMRKIT_DEMO_MODE"), default=False),
        max_upload_mb=_parse_positive_int(os.environ.get("OMRKIT_MAX_UPLOAD_MB"), default=15),
        max_files_per_scan=_parse_positive_int(
            os.environ.get("OMRKIT_MAX_FILES_PER_SCAN"), default=20
        ),
        max_pdf_pages=_parse_positive_int(os.environ.get("OMRKIT_MAX_PDF_PAGES"), default=25),
    )
