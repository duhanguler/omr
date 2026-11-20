"""Scan output, bubble reading, and HITL review queue models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FieldStatus = Literal["ok", "blank", "multi_marked", "low_confidence", "invalid_checksum"]


class BubbleReading(BaseModel):
    """Per-bubble optical measurements from the hybrid detector."""

    option: str
    cx: float
    cy: float
    radius: float
    fill_ratio: float = Field(ge=0.0, le=1.0)
    darkness: float = Field(ge=0.0, le=1.0)
    ink_score: float = Field(ge=0.0, le=1.0)
    combined_score: float = Field(ge=0.0, le=1.0)
    selected: bool = False


class FieldReading(BaseModel):
    """Evaluated reading for a single OMR field (question or ID digit)."""

    field_id: str
    block_name: str
    value: str
    selected_options: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    status: FieldStatus = "ok"
    bubbles: list[BubbleReading] = Field(default_factory=list)


class ReviewItem(BaseModel):
    """Actionable item queued for Human-in-the-Loop (HITL) verification."""

    field_id: str
    block_name: str
    reason: FieldStatus
    suggested_value: str
    confidence: float = Field(ge=0.0, le=1.0)
    candidate_options: list[str] = Field(default_factory=list)
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2) in canonical coordinates
    message: str = ""


class SheetResult(BaseModel):
    """Complete scan output for a single optical sheet page."""

    sheet_id: str
    source_file: str
    page_index: int = 0
    template_name: str
    fields: dict[str, FieldReading] = Field(default_factory=dict)
    grouped_values: dict[str, str] = Field(default_factory=dict)
    review_items: list[ReviewItem] = Field(default_factory=list)
    overall_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    registration_method: str = "none"
    registration_score: float = Field(default=1.0, ge=0.0, le=1.0)
    rotation_applied: int = 0
    elapsed_ms: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None

    def flat_responses(self) -> dict[str, str]:
        """Return flat mapping of field/group labels to resolved string values."""
        output: dict[str, str] = {}
        for field_id, reading in self.fields.items():
            output[field_id] = reading.value
        output.update(self.grouped_values)
        return output

    def apply_override(self, field_id: str, new_value: str) -> None:
        """Apply a human-in-the-loop correction and clear the corresponding review flag."""
        if field_id in self.fields:
            reading = self.fields[field_id]
            reading.value = new_value
            valid_options = {b.option for b in reading.bubbles}
            if not new_value:
                selected_opts: list[str] = []
            elif new_value in valid_options:
                selected_opts = [new_value]
            else:
                selected_opts = list(new_value)
            reading.selected_options = selected_opts
            selected_set = set(selected_opts)
            for bubble in reading.bubbles:
                bubble.selected = bubble.option in selected_set
            reading.confidence = 1.0
            reading.status = "blank" if new_value == "" else "ok"
            if self.fields:
                self.overall_confidence = round(
                    sum(f.confidence for f in self.fields.values()) / float(len(self.fields)),
                    4,
                )
        elif field_id in self.grouped_values:
            self.grouped_values[field_id] = new_value
        self.review_items = [item for item in self.review_items if item.field_id != field_id]


class BatchResult(BaseModel):
    """Aggregated outcome of scanning multiple images or multi-page PDFs."""

    template_name: str
    sheets: list[SheetResult] = Field(default_factory=list)
    total_sheets: int = 0
    succeeded: int = 0
    flagged_sheets: int = 0
    failed_sheets: int = 0
    total_elapsed_ms: float = 0.0
    sheets_per_minute: float = 0.0
