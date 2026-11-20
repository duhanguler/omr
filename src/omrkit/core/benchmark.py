"""Synthetic distortion benchmark harness for measuring OMR accuracy and throughput."""

from __future__ import annotations

import random
from dataclasses import dataclass
from time import perf_counter

import cv2
import numpy as np

from omrkit.core.scanner import OMRScanner
from omrkit.generator.pdf_sheet import SheetGenerator
from omrkit.generator.presets import get_sheet_preset
from omrkit.io.loader import load_bytes
from omrkit.models.template import Template
from omrkit.vision.preprocess import rotate_image


@dataclass(slots=True)
class BenchmarkScenarioResult:
    """Accuracy and throughput metrics for one camera/marking distortion scenario."""

    scenario: str
    sheets: int
    total_fields: int
    correct_fields: int
    accuracy_pct: float
    avg_confidence: float
    flagged_fields: int
    sheets_per_minute: float


def render_synthetic_filled_sheet(
    blank_bgr: np.ndarray,
    template: Template,
    answers: dict[str, str],
    mark_style: str = "solid",
    seed: int = 42,
) -> np.ndarray:
    """Programmatically mark known answers onto a rendered blank optical sheet."""
    rng = random.Random(seed)
    img = blank_bgr.copy()

    for block in template.blocks:
        for field_id, coords in block.iter_field_bubbles():
            expected = answers.get(field_id, "")
            if not expected:
                continue
            valid_opts = {c.option for c in coords}
            target_opts = {expected} if expected in valid_opts else set(expected)
            for coord in coords:
                if coord.option not in target_opts:
                    continue
                cx = round(coord.cx + rng.uniform(-1.0, 1.0))
                cy = round(coord.cy + rng.uniform(-1.0, 1.0))
                r = max(4, round(coord.radius))
                ink_tone = rng.randint(25, 58)
                color = (ink_tone, ink_tone, ink_tone)

                if mark_style == "solid":
                    cv2.circle(img, (cx, cy), int(r * 0.80), color, -1, cv2.LINE_AA)
                elif mark_style == "checkmark":
                    p1 = (cx - int(r * 0.55), cy)
                    p2 = (cx - int(r * 0.10), cy + int(r * 0.50))
                    p3 = (cx + int(r * 0.65), cy - int(r * 0.55))
                    thickness = max(3, int(r * 0.28))
                    cv2.line(img, p1, p2, color, thickness, cv2.LINE_AA)
                    cv2.line(img, p2, p3, color, thickness, cv2.LINE_AA)
                elif mark_style == "cross":
                    d = int(r * 0.55)
                    thickness = max(3, int(r * 0.26))
                    cv2.line(img, (cx - d, cy - d), (cx + d, cy + d), color, thickness, cv2.LINE_AA)
                    cv2.line(img, (cx - d, cy + d), (cx + d, cy - d), color, thickness, cv2.LINE_AA)
    result_img: np.ndarray = img
    return result_img


def apply_camera_distortion(
    img_bgr: np.ndarray,
    rotation_deg: int = 0,
    perspective_strength: float = 0.0,
    shadow_strength: float = 0.0,
    blur_sigma: float = 0.0,
    seed: int = 42,
) -> np.ndarray:
    """Simulate mobile camera perspective skew, shadows, rotation, and lens blur."""
    rng = random.Random(seed)
    out: np.ndarray = img_bgr.copy()

    if shadow_strength > 0:
        h, w = out.shape[:2]
        grad_x = np.linspace(1.0 - shadow_strength, 1.0, w, dtype=np.float32)
        grad_y = np.linspace(1.0, 1.0 - shadow_strength * 0.6, h, dtype=np.float32)
        mask = np.outer(grad_y, grad_x)[:, :, None]
        out = np.clip(out.astype(np.float32) * mask, 0, 255).astype(np.uint8)

    if perspective_strength > 0:
        h, w = out.shape[:2]
        pad = int(min(h, w) * 0.08)
        bordered = cv2.copyMakeBorder(
            out, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(210, 205, 198)
        )
        bh, bw = bordered.shape[:2]
        jitter = min(bh, bw) * perspective_strength
        src = np.asarray([[0, 0], [bw - 1, 0], [bw - 1, bh - 1], [0, bh - 1]], dtype=np.float32)
        dst = np.asarray(
            [
                [rng.uniform(0, jitter), rng.uniform(0, jitter)],
                [bw - 1 - rng.uniform(0, jitter), rng.uniform(0, jitter)],
                [bw - 1 - rng.uniform(0, jitter), bh - 1 - rng.uniform(0, jitter)],
                [rng.uniform(0, jitter), bh - 1 - rng.uniform(0, jitter)],
            ],
            dtype=np.float32,
        )
        mat = cv2.getPerspectiveTransform(src, dst)
        out = cv2.warpPerspective(
            bordered, mat, (bw, bh), borderMode=cv2.BORDER_CONSTANT, borderValue=(195, 190, 185)
        )

    if rotation_deg % 360 != 0:
        out = rotate_image(out, rotation_deg)

    if blur_sigma > 0:
        out = cv2.GaussianBlur(out, (0, 0), sigmaX=blur_sigma)

    return out


def run_benchmark(
    preset_id: str = "standard_mcq_40",
    samples_per_scenario: int = 5,
) -> list[BenchmarkScenarioResult]:
    """Run an end-to-end accuracy and speed benchmark across realistic scan scenarios."""
    spec = get_sheet_preset(preset_id)
    generated = SheetGenerator().generate(spec)
    blank_page = load_bytes(generated.pdf_bytes, f"{preset_id}.pdf", dpi=spec.dpi)[0]
    template = generated.template
    scanner = OMRScanner(template)

    scenarios = [
        ("Clean Flatbed Scan (Solid Fill)", "solid", 0, 0.0, 0.0, 0.0),
        ("Mobile Perspective + Shadow", "solid", 0, 0.055, 0.35, 0.7),
        ("Rotated 90/180/270 + Perspective", "solid", -1, 0.045, 0.25, 0.5),
        ("Pen Checkmarks (✓) + Shadow", "checkmark", 0, 0.03, 0.25, 0.4),
    ]

    results: list[BenchmarkScenarioResult] = []
    for s_idx, (name, style, rot_mode, persp, shadow, blur) in enumerate(scenarios):
        total_fields = 0
        correct_fields = 0
        flagged_fields = 0
        confs: list[float] = []
        t0 = perf_counter()

        for i in range(samples_per_scenario):
            seed = 1000 + s_idx * 100 + i
            rng = random.Random(seed)
            ground_truth: dict[str, str] = {}
            for block in template.blocks:
                for field_id in block.expanded_labels():
                    # Leave ~10% MCQ questions intentionally blank
                    if block.field_type == "mcq" and rng.random() < 0.10:
                        ground_truth[field_id] = ""
                    else:
                        ground_truth[field_id] = rng.choice(block.options)

            marked = render_synthetic_filled_sheet(
                blank_page.image_bgr, template, ground_truth, mark_style=style, seed=seed
            )
            rot = [90, 180, 270][i % 3] if rot_mode == -1 else rot_mode
            distorted = apply_camera_distortion(
                marked,
                rotation_deg=rot,
                perspective_strength=persp,
                shadow_strength=shadow,
                blur_sigma=blur,
                seed=seed,
            )

            scan_res, _ = scanner.scan_image(distorted, source_name=f"bench_{s_idx}_{i}.png")
            confs.append(scan_res.overall_confidence)
            flagged_fields += len(scan_res.review_items)

            for field_id, expected in ground_truth.items():
                total_fields += 1
                got = scan_res.fields[field_id].value if field_id in scan_res.fields else "__ERR__"
                if got == expected:
                    correct_fields += 1

        elapsed_min = max(1e-6, (perf_counter() - t0) / 60.0)
        acc = (correct_fields / float(total_fields) * 100.0) if total_fields else 0.0
        results.append(
            BenchmarkScenarioResult(
                scenario=name,
                sheets=samples_per_scenario,
                total_fields=total_fields,
                correct_fields=correct_fields,
                accuracy_pct=round(acc, 2),
                avg_confidence=round(float(np.mean(confs)) if confs else 0.0, 4),
                flagged_fields=flagged_fields,
                sheets_per_minute=round(samples_per_scenario / elapsed_min, 1),
            )
        )

    return results
