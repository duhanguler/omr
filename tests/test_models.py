"""Unit tests for Pydantic Template, FieldBlock, and label expansion models."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from omrkit.models import (
    DetectionConfig,
    FieldBlock,
    RegistrationConfig,
    Template,
    expand_field_labels,
)


def test_expand_field_labels_ranges_and_zero_padding() -> None:
    assert expand_field_labels(["q1..4"]) == ["q1", "q2", "q3", "q4"]
    assert expand_field_labels(["id01..03", "extra"]) == ["id01", "id02", "id03", "extra"]


def test_expand_field_labels_rejects_invalid_and_duplicate() -> None:
    with pytest.raises(ValueError, match="must be >="):
        expand_field_labels(["q5..2"])
    with pytest.raises(ValueError, match="Duplicate"):
        expand_field_labels(["q1..3", "q2"])


def test_template_rejects_out_of_bounds_bubbles() -> None:
    with pytest.raises(ValidationError, match="exceeds page dimensions"):
        Template(
            name="overflow",
            page_width=200,
            page_height=200,
            registration=RegistrationConfig(mode="none"),
            blocks=[
                FieldBlock(
                    name="B1",
                    origin=(150, 150),
                    bubble_radius=20,
                    bubbles_gap=45,
                    labels_gap=45,
                    options=["A", "B", "C"],
                    labels=["q1..3"],
                )
            ],
        )


def test_template_rejects_overlapping_field_labels() -> None:
    with pytest.raises(ValidationError, match="overlaps"):
        Template(
            name="overlap",
            page_width=800,
            page_height=800,
            registration=RegistrationConfig(mode="none"),
            blocks=[
                FieldBlock(
                    name="B1",
                    origin=(100, 100),
                    bubble_radius=12,
                    bubbles_gap=35,
                    labels_gap=35,
                    options=["A", "B"],
                    labels=["q1..3"],
                ),
                FieldBlock(
                    name="B2",
                    origin=(300, 100),
                    bubble_radius=12,
                    bubbles_gap=35,
                    labels_gap=35,
                    options=["A", "B"],
                    labels=["q3..5"],
                ),
            ],
        )


def test_detection_config_validates_threshold_order() -> None:
    with pytest.raises(ValidationError, match="blank_floor"):
        DetectionConfig(fill_threshold=0.20, blank_floor=0.25)


def test_template_json_and_yaml_roundtrip(tmp_path: Path) -> None:
    tmpl = Template(
        name="roundtrip_test",
        page_width=600,
        page_height=800,
        registration=RegistrationConfig(mode="none"),
        blocks=[
            FieldBlock(
                name="MCQ",
                origin=(80, 100),
                bubble_radius=12,
                bubbles_gap=40,
                labels_gap=42,
                options=["A", "B", "C", "D"],
                labels=["q1..5"],
            )
        ],
    )
    json_path = tmpl.to_file(tmp_path / "template.json")
    yaml_path = tmpl.to_file(tmp_path / "template.yaml")

    assert Template.from_file(json_path).all_field_ids() == ["q1", "q2", "q3", "q4", "q5"]
    assert Template.from_file(yaml_path).name == "roundtrip_test"
