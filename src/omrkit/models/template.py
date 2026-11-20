"""Template, field block, and registration schemas for OMRKit."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

RegistrationMode = Literal["aruco", "markers", "page_quad", "homography", "none"]
FieldType = Literal["mcq", "grid_digits", "grid_alpha", "custom"]
BlockDirection = Literal["horizontal", "vertical"]
OriginMode = Literal["center", "top_left"]
ValidatorType = Literal["tr_tckn", "luhn", "digits", "non_empty"]

_RANGE_PATTERN = re.compile(r"^([^\.\d]+)(\d+)\.{2,3}(\d+)$")


def expand_field_labels(raw_labels: list[str]) -> list[str]:
    """Expand concise range expressions such as 'q1..25' or 'id01..11'."""
    expanded: list[str] = []
    seen: set[str] = set()
    for token in raw_labels:
        match = _RANGE_PATTERN.match(token)
        if match:
            prefix, start_s, end_s = match.groups()
            start, end = int(start_s), int(end_s)
            if end < start:
                raise ValueError(
                    f"Invalid label range '{token}': end ({end}) must be >= start ({start})."
                )
            pad = len(start_s) if start_s.startswith("0") and len(start_s) > 1 else 0
            for idx in range(start, end + 1):
                label = f"{prefix}{idx:0{pad}d}" if pad else f"{prefix}{idx}"
                if label in seen:
                    raise ValueError(f"Duplicate expanded label '{label}' in '{token}'.")
                seen.add(label)
                expanded.append(label)
        else:
            if token in seen:
                raise ValueError(f"Duplicate label '{token}'.")
            seen.add(token)
            expanded.append(token)
    return expanded


class BubbleCoord(BaseModel):
    """Canonical coordinate specification for a single bubble."""

    field_id: str
    option: str
    cx: float
    cy: float
    radius: float


class RegistrationConfig(BaseModel):
    """Page alignment and perspective rectification settings."""

    mode: RegistrationMode = "aruco"
    aruco_dict: str = "DICT_4X4_50"
    aruco_ids: tuple[int, int, int, int] = (0, 1, 2, 3)
    target_corners: list[tuple[float, float]] | None = None

    # Concentric / custom template marker mode
    marker_path: str | None = None
    sheet_to_marker_width_ratio: float = Field(default=17.0, gt=1.0)
    min_match_score: float = Field(default=0.30, ge=0.0, le=1.0)
    max_match_variation: float = Field(default=0.45, ge=0.0, le=1.0)
    scale_range: tuple[float, float] = (0.35, 1.15)
    scale_steps: int = Field(default=16, ge=2, le=64)
    split_ratio_x: float = Field(default=0.50, gt=0.1, lt=0.9)
    split_ratio_y: float = Field(default=0.50, gt=0.1, lt=0.9)
    erode_subtract: bool = True
    auto_rotate: bool = True

    # Page quad mode
    min_area_ratio: float = Field(default=0.18, gt=0.01, lt=1.0)
    morph_kernel: tuple[int, int] = (9, 9)

    # Feature-based homography mode
    reference_path: str | None = None
    max_features: int = Field(default=1500, ge=100, le=10000)
    good_match_ratio: float = Field(default=0.20, gt=0.02, le=1.0)

    @model_validator(mode="after")
    def _validate_target_corners(self) -> RegistrationConfig:
        if self.target_corners is not None and len(self.target_corners) != 4:
            raise ValueError("target_corners must contain exactly 4 (x, y) coordinates.")
        if self.scale_range[0] <= 0 or self.scale_range[1] <= self.scale_range[0]:
            raise ValueError("scale_range must satisfy 0 < min_scale < max_scale.")
        return self


class DetectionConfig(BaseModel):
    """Hybrid shape-aware bubble detection and HITL confidence parameters."""

    fill_threshold: float = Field(default=0.26, gt=0.0, lt=1.0)
    blank_floor: float = Field(default=0.14, ge=0.0, lt=1.0)
    min_separation: float = Field(default=0.09, ge=0.0, lt=1.0)
    review_confidence_threshold: float = Field(default=0.72, ge=0.0, le=1.0)
    inner_radius_ratio: float = Field(default=0.70, gt=0.2, le=1.0)
    ring_inner_ratio: float = Field(default=1.12, gt=1.0, le=2.0)
    ring_outer_ratio: float = Field(default=1.48, gt=1.1, le=2.5)
    fill_delta: float = Field(default=22.0, gt=1.0, le=150.0)
    ink_delta: float = Field(default=36.0, gt=1.0, le=200.0)
    multi_mark_ratio: float = Field(default=0.70, gt=0.2, le=1.0)
    normalize_illumination: bool = True

    @model_validator(mode="after")
    def _validate_thresholds(self) -> DetectionConfig:
        if self.blank_floor >= self.fill_threshold:
            raise ValueError("blank_floor must be strictly smaller than fill_threshold.")
        if self.ring_outer_ratio <= self.ring_inner_ratio:
            raise ValueError("ring_outer_ratio must be greater than ring_inner_ratio.")
        return self


class FieldBlock(BaseModel):
    """A structured rectangular grid of bubbles representing one or more fields."""

    name: str = Field(min_length=1)
    field_type: FieldType = "mcq"
    direction: BlockDirection = "horizontal"
    origin: tuple[float, float]
    origin_mode: OriginMode = "center"
    bubble_radius: float = Field(default=14.0, gt=2.0)
    bubbles_gap: float = Field(gt=2.0)
    labels_gap: float = Field(gt=2.0)
    options: list[str] = Field(min_length=1)
    labels: list[str] = Field(min_length=1)
    allow_multiple: bool = False
    empty_value: str = ""
    group_as: str | None = None
    validator: ValidatorType | None = None

    @field_validator("options")
    @classmethod
    def _unique_options(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Bubble options within a FieldBlock must be unique.")
        return value

    def expanded_labels(self) -> list[str]:
        """Return fully expanded field labels in display order."""
        return expand_field_labels(self.labels)

    def iter_field_bubbles(self) -> list[tuple[str, list[BubbleCoord]]]:
        """Generate exact canonical bubble center coordinates for every field in this block."""
        labels = self.expanded_labels()
        start_x, start_y = self.origin
        if self.origin_mode == "top_left":
            start_x += self.bubble_radius
            start_y += self.bubble_radius

        fields: list[tuple[str, list[BubbleCoord]]] = []
        for field_idx, field_id in enumerate(labels):
            coords: list[BubbleCoord] = []
            for opt_idx, option in enumerate(self.options):
                if self.direction == "horizontal":
                    cx = start_x + opt_idx * self.bubbles_gap
                    cy = start_y + field_idx * self.labels_gap
                else:
                    cx = start_x + field_idx * self.labels_gap
                    cy = start_y + opt_idx * self.bubbles_gap
                coords.append(
                    BubbleCoord(
                        field_id=field_id,
                        option=option,
                        cx=round(cx, 2),
                        cy=round(cy, 2),
                        radius=self.bubble_radius,
                    )
                )
            fields.append((field_id, coords))
        return fields


class Template(BaseModel):
    """Complete OMR sheet layout, registration, and detection specification."""

    version: str = "2.0"
    name: str = Field(min_length=1)
    description: str = ""
    page_width: int = Field(gt=50)
    page_height: int = Field(gt=50)
    registration: RegistrationConfig = Field(default_factory=RegistrationConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    blocks: list[FieldBlock] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_layout(self) -> Template:
        block_names: set[str] = set()
        seen_fields: set[str] = set()
        margin = 1.0

        for block in self.blocks:
            if block.name in block_names:
                raise ValueError(f"Duplicate block name '{block.name}'.")
            block_names.add(block.name)

            for field_id, bubbles in block.iter_field_bubbles():
                if field_id in seen_fields:
                    raise ValueError(
                        f"Field label '{field_id}' in block '{block.name}' overlaps an existing field."
                    )
                seen_fields.add(field_id)

                for bubble in bubbles:
                    if (
                        bubble.cx - bubble.radius < -margin
                        or bubble.cy - bubble.radius < -margin
                        or bubble.cx + bubble.radius > self.page_width + margin
                        or bubble.cy + bubble.radius > self.page_height + margin
                    ):
                        raise ValueError(
                            f"Bubble '{field_id}:{bubble.option}' in block '{block.name}' "
                            f"at ({bubble.cx}, {bubble.cy}, r={bubble.radius}) exceeds page "
                            f"dimensions ({self.page_width}x{self.page_height})."
                        )
        return self

    def all_field_ids(self) -> list[str]:
        """Return ordered list of all expanded field IDs."""
        ids: list[str] = []
        for block in self.blocks:
            ids.extend(block.expanded_labels())
        return ids

    def grouped_field_names(self) -> list[str]:
        """Return names of logical output columns (grouped blocks collapse into one column)."""
        columns: list[str] = []
        for block in self.blocks:
            if block.group_as:
                if block.group_as not in columns:
                    columns.append(block.group_as)
            else:
                columns.extend(block.expanded_labels())
        return columns

    @classmethod
    def from_file(cls, path: str | Path) -> Template:
        """Load and validate a Template from JSON or YAML."""
        file_path = Path(path)
        raw = file_path.read_text(encoding="utf-8")
        if file_path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
        template = cls.model_validate(data)
        # Resolve relative registration asset paths against the template's parent directory
        if template.registration.marker_path:
            marker_p = Path(template.registration.marker_path)
            if not marker_p.is_absolute():
                resolved = file_path.parent / marker_p
                if resolved.exists():
                    template.registration.marker_path = str(resolved)
        if template.registration.reference_path:
            ref_p = Path(template.registration.reference_path)
            if not ref_p.is_absolute():
                resolved = file_path.parent / ref_p
                if resolved.exists():
                    template.registration.reference_path = str(resolved)
        return template

    def to_file(self, path: str | Path) -> Path:
        """Serialize the template to JSON or YAML."""
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
