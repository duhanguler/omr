"""One-command migrator converting legacy OMRChecker v1 template.json files to OMRKit v2.0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omrkit.models.template import (
    BlockDirection,
    DetectionConfig,
    FieldBlock,
    FieldType,
    RegistrationConfig,
    Template,
)

_LEGACY_FIELD_TYPES: dict[str, tuple[list[str], BlockDirection, FieldType]] = {
    "QTYPE_INT": ([str(i) for i in range(10)], "vertical", "grid_digits"),
    "QTYPE_INT_FROM_1": ([str(i) for i in range(1, 10)] + ["0"], "vertical", "grid_digits"),
    "QTYPE_MCQ4": (["A", "B", "C", "D"], "horizontal", "mcq"),
    "QTYPE_MCQ5": (["A", "B", "C", "D", "E"], "horizontal", "mcq"),
}


def migrate_legacy_template_dict(
    legacy: dict[str, Any],
    name: str = "migrated_template",
) -> Template:
    """Convert an OMRChecker-format template dictionary into a validated OMRKit v2.0 Template."""
    page_dims = legacy.get("pageDimensions")
    bubble_dims = legacy.get("bubbleDimensions", [24, 24])
    if not isinstance(page_dims, list) or len(page_dims) != 2:
        raise ValueError("Legacy template must define 'pageDimensions': [width, height].")

    page_w, page_h = int(page_dims[0]), int(page_dims[1])
    default_radius = max(4.0, round(min(float(bubble_dims[0]), float(bubble_dims[1])) / 2.0, 2))
    global_empty = str(legacy.get("emptyValue", ""))

    # Translate preProcessors -> RegistrationConfig
    registration = RegistrationConfig(mode="none")
    for pp in legacy.get("preProcessors", []):
        pp_name = pp.get("name")
        opts = pp.get("options", {})
        if pp_name == "CropOnMarkers":
            registration = RegistrationConfig(
                mode="markers",
                marker_path=opts.get("relativePath"),
                sheet_to_marker_width_ratio=float(opts.get("sheetToMarkerWidthRatio", 17.0)),
                min_match_score=float(opts.get("min_matching_threshold", 0.30)),
                max_match_variation=float(opts.get("max_matching_variation", 0.45)),
                erode_subtract=bool(opts.get("apply_erode_subtract", True)),
                auto_rotate=True,
            )
            break
        if pp_name == "CropPage":
            mk = opts.get("morphKernel", [10, 10])
            registration = RegistrationConfig(
                mode="page_quad",
                morph_kernel=(int(mk[0]), int(mk[1])),
            )
            break
        if pp_name == "FeatureBasedAlignment":
            registration = RegistrationConfig(
                mode="homography",
                reference_path=opts.get("reference"),
                max_features=int(opts.get("maxFeatures", 1500)),
                good_match_ratio=float(opts.get("goodMatchPercent", 0.20)),
            )
            break

    # Build lookup from exact field label list -> customLabel group name
    custom_groups: dict[tuple[str, ...], str] = {}
    for group_name, label_list in legacy.get("customLabels", {}).items():
        if isinstance(label_list, list):
            custom_groups[tuple(str(x) for x in label_list)] = str(group_name)

    blocks: list[FieldBlock] = []
    field_blocks = legacy.get("fieldBlocks", {})
    if not isinstance(field_blocks, dict) or not field_blocks:
        raise ValueError("Legacy template must define a non-empty 'fieldBlocks' mapping.")

    for block_name, cfg in field_blocks.items():
        legacy_ft = cfg.get("fieldType")
        if legacy_ft in _LEGACY_FIELD_TYPES:
            options, direction, ftype = _LEGACY_FIELD_TYPES[legacy_ft]
        else:
            options = [str(v) for v in cfg.get("bubbleValues", ["A", "B", "C", "D"])]
            raw_dir = str(cfg.get("direction", "vertical"))
            direction = "horizontal" if raw_dir == "horizontal" else "vertical"
            ftype = "custom"

        if "direction" in cfg:
            direction = "horizontal" if cfg["direction"] == "horizontal" else "vertical"
        if "bubbleValues" in cfg:
            options = [str(v) for v in cfg["bubbleValues"]]

        blk_dims = cfg.get("bubbleDimensions")
        radius = (
            max(4.0, round(min(float(blk_dims[0]), float(blk_dims[1])) / 2.0, 2))
            if isinstance(blk_dims, list) and len(blk_dims) == 2
            else default_radius
        )

        labels = [str(x) for x in cfg["fieldLabels"]]
        group_as = custom_groups.get(tuple(labels))
        origin_raw = cfg["origin"]

        blocks.append(
            FieldBlock(
                name=str(block_name),
                field_type=ftype,
                direction=direction,
                origin=(float(origin_raw[0]), float(origin_raw[1])),
                origin_mode="top_left",
                bubble_radius=radius,
                bubbles_gap=float(cfg["bubblesGap"]),
                labels_gap=float(cfg["labelsGap"]),
                options=options,
                labels=labels,
                empty_value=str(cfg.get("emptyValue", global_empty)),
                group_as=group_as,
            )
        )

    return Template(
        version="2.0",
        name=name,
        description="Migrated from legacy OMRChecker template format.",
        page_width=page_w,
        page_height=page_h,
        registration=registration,
        detection=DetectionConfig(),
        blocks=blocks,
        metadata={"migrated_from": "omrchecker_v1"},
    )


def migrate_legacy_template_file(
    src_path: str | Path,
    dst_path: str | Path | None = None,
) -> Template:
    """Load a legacy OMRChecker template JSON file, migrate to v2.0, and optionally save."""
    src = Path(src_path)
    raw = json.loads(src.read_text(encoding="utf-8"))
    template = migrate_legacy_template_dict(raw, name=src.stem)
    if dst_path is not None:
        template.to_file(dst_path)
    return template
