"""End-to-end tests for SheetGenerator presets and HybridBubbleDetector edge cases."""

from __future__ import annotations

import cv2
import pytest

from omrkit.core.benchmark import render_synthetic_filled_sheet
from omrkit.core.scanner import OMRScanner
from omrkit.generator import SheetGenerator, get_sheet_preset
from omrkit.io.loader import load_bytes


@pytest.mark.parametrize(
    "preset_id",
    ["quick_quiz_20", "standard_mcq_40", "turkish_exam_50", "turkish_yks_120"],
)
def test_all_presets_generate_and_roundtrip_perfectly(preset_id: str) -> None:
    spec = get_sheet_preset(preset_id)
    gen = SheetGenerator().generate(spec)
    assert gen.pdf_bytes.startswith(b"%PDF")

    page = load_bytes(gen.pdf_bytes, f"{preset_id}.pdf", dpi=spec.dpi)[0]
    gt: dict[str, str] = {}
    for idx, block in enumerate(gen.template.blocks):
        for f_idx, fid in enumerate(block.expanded_labels()):
            if block.field_type == "mcq" and f_idx % 9 == 0:
                gt[fid] = ""
            else:
                gt[fid] = block.options[(idx + f_idx) % len(block.options)]

    # For TC Kimlik No, mark a mathematically valid TCKN so checksum validator passes
    if preset_id == "turkish_exam_50":
        valid_tckn = "10000000146"
        for i, digit in enumerate(valid_tckn, start=1):
            gt[f"tc_kimlik_no_{i}"] = digit

    marked = render_synthetic_filled_sheet(page.image_bgr, gen.template, gt, seed=123)
    res, _ = OMRScanner(gen.template).scan_image(marked, source_name=f"{preset_id}.png")

    assert res.error is None
    assert len(res.review_items) == 0
    for fid, expected in gt.items():
        assert res.fields[fid].value == expected


def test_detector_flags_multimark_and_handles_checkmarks_and_override() -> None:
    spec = get_sheet_preset("quick_quiz_20")
    gen = SheetGenerator().generate(spec)
    blank = load_bytes(gen.pdf_bytes, "quiz.pdf", dpi=spec.dpi)[0].image_bgr

    # q1: checkmark on B, q2: cross on C, q3: multi-marked A and D, q4: faint smudge on B, q5: blank
    img = render_synthetic_filled_sheet(blank, gen.template, {"q1": "B"}, mark_style="checkmark")
    img = render_synthetic_filled_sheet(img, gen.template, {"q2": "C"}, mark_style="cross")
    img = render_synthetic_filled_sheet(img, gen.template, {"q3": "AD"}, mark_style="solid")

    # Add an intentional faint smudge on q4 option B
    q4_b = next(
        c
        for blk in gen.template.blocks
        for fid, coords in blk.iter_field_bubbles()
        if fid == "q4"
        for c in coords
        if c.option == "B"
    )
    cv2.circle(
        img, (round(q4_b.cx), round(q4_b.cy)), round(q4_b.radius * 0.45), (195, 195, 195), -1
    )

    res, _ = OMRScanner(gen.template).scan_image(img, source_name="edge_cases.png")
    assert res.fields["q1"].value == "B"
    assert res.fields["q2"].value == "C"
    assert res.fields["q3"].status == "multi_marked"
    assert res.fields["q3"].value == "AD"
    assert res.fields["q5"].status == "blank"

    flagged_ids = {item.field_id for item in res.review_items}
    assert "q3" in flagged_ids

    # Apply HITL override and verify review flag clears
    res.apply_override("q3", "A")
    assert res.fields["q3"].value == "A"
    assert res.fields["q3"].status == "ok"
    assert "q3" not in {item.field_id for item in res.review_items}
