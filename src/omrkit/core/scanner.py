"""High-level single-sheet and parallel batch OMR scanning engine."""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from omrkit.core.validators import run_validator
from omrkit.io.loader import (
    DocumentLoadError,
    LoadedPage,
    discover_documents,
    load_bytes,
    load_document,
)
from omrkit.models.scan import BatchResult, ReviewItem, SheetResult
from omrkit.models.template import Template
from omrkit.vision.detector import HybridBubbleDetector
from omrkit.vision.registration import RegistrationError, register_sheet
from omrkit.vision.visualizer import render_annotated_sheet


def _scan_single_file_worker(
    args: tuple[str, dict[str, object], int, str | None],
) -> list[dict[str, object]]:
    """Top-level picklable worker function for ProcessPoolExecutor batch scanning."""
    file_path_str, template_dict, dpi, overlay_dir_str = args
    template = Template.model_validate(template_dict)
    scanner = OMRScanner(template=template, dpi=dpi)
    overlay_dir = Path(overlay_dir_str) if overlay_dir_str else None
    results = scanner.scan_file(file_path_str, save_overlay_dir=overlay_dir)
    return [r.model_dump(mode="json") for r in results]


class OMRScanner:
    """Scans single images, multi-page PDFs, or folders against an OMRKit Template."""

    def __init__(
        self,
        template: Template,
        detector: HybridBubbleDetector | None = None,
        dpi: int = 200,
    ) -> None:
        self.template = template
        self.detector = detector or HybridBubbleDetector(template.detection)
        self.dpi = dpi

    def scan_page(
        self,
        page: LoadedPage,
        save_overlay_dir: str | Path | None = None,
    ) -> tuple[SheetResult, np.ndarray | None]:
        """Scan one decoded page and return (SheetResult, aligned_warped_bgr)."""
        t0 = perf_counter()
        stem = Path(page.source_name).stem
        sheet_id = f"{stem}_p{page.page_index + 1}" if page.page_index > 0 else stem

        try:
            reg = register_sheet(page.image_bgr, self.template)
        except RegistrationError as exc:
            elapsed = (perf_counter() - t0) * 1000.0
            return (
                SheetResult(
                    sheet_id=sheet_id,
                    source_file=page.source_name,
                    page_index=page.page_index,
                    template_name=self.template.name,
                    overall_confidence=0.0,
                    registration_method=self.template.registration.mode,
                    registration_score=0.0,
                    elapsed_ms=round(elapsed, 2),
                    error=str(exc),
                ),
                None,
            )

        fields, review_items = self.detector.detect_sheet(reg.warped_bgr, self.template)

        # Assemble grouped values (e.g., multi-column Student ID / TC Kimlik No)
        grouped_values: dict[str, str] = {}
        warnings: list[str] = []

        for block in self.template.blocks:
            labels = block.expanded_labels()
            if block.group_as:
                joined = "".join(fields[lbl].value for lbl in labels)
                grouped_values[block.group_as] = joined
                if block.validator is not None:
                    valid, msg = run_validator(block.validator, joined)
                    if not valid:
                        warnings.append(msg)
                        all_bubbles = [b for lbl in labels for b in fields[lbl].bubbles]
                        xs = [b.cx for b in all_bubbles]
                        ys = [b.cy for b in all_bubbles]
                        pad = max(20.0, block.bubble_radius * 2.0)
                        bbox = (
                            max(0, int(min(xs) - pad)),
                            max(0, int(min(ys) - pad)),
                            int(max(xs) + pad),
                            int(max(ys) + pad),
                        )
                        review_items.append(
                            ReviewItem(
                                field_id=block.group_as,
                                block_name=block.name,
                                reason="invalid_checksum",
                                suggested_value=joined,
                                confidence=0.4,
                                candidate_options=[],
                                bbox=bbox,
                                message=msg,
                            )
                        )
            elif block.validator is not None:
                for lbl in labels:
                    val = fields[lbl].value
                    valid, msg = run_validator(block.validator, val)
                    if not valid:
                        fields[lbl].status = "invalid_checksum"
                        warnings.append(f"{lbl}: {msg}")
                        field_bubbles = fields[lbl].bubbles
                        xs = [b.cx for b in field_bubbles] or [0.0]
                        ys = [b.cy for b in field_bubbles] or [0.0]
                        pad = max(18.0, block.bubble_radius * 2.2)
                        bbox = (
                            max(0, int(min(xs) - pad)),
                            max(0, int(min(ys) - pad)),
                            int(max(xs) + pad),
                            int(max(ys) + pad),
                        )
                        review_items.append(
                            ReviewItem(
                                field_id=lbl,
                                block_name=block.name,
                                reason="invalid_checksum",
                                suggested_value=val,
                                confidence=min(fields[lbl].confidence, 0.4),
                                candidate_options=[b.option for b in field_bubbles],
                                bbox=bbox,
                                message=msg,
                            )
                        )

        confidences = [f.confidence for f in fields.values()]
        overall_conf = round(float(np.mean(confidences)) if confidences else 0.0, 4)
        elapsed = (perf_counter() - t0) * 1000.0

        result = SheetResult(
            sheet_id=sheet_id,
            source_file=page.source_name,
            page_index=page.page_index,
            template_name=self.template.name,
            fields=fields,
            grouped_values=grouped_values,
            review_items=review_items,
            overall_confidence=overall_conf,
            registration_method=reg.method,
            registration_score=reg.score,
            rotation_applied=reg.rotation_deg,
            elapsed_ms=round(elapsed, 2),
            warnings=warnings,
        )

        if save_overlay_dir is not None:
            out_dir = Path(save_overlay_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            overlay = render_annotated_sheet(reg.warped_bgr, result)
            cv2.imwrite(str(out_dir / f"{sheet_id}_overlay.png"), overlay)

        return result, reg.warped_bgr

    def scan_image(
        self,
        image_bgr: np.ndarray,
        source_name: str = "image.png",
        page_index: int = 0,
    ) -> tuple[SheetResult, np.ndarray | None]:
        """Scan an in-memory OpenCV BGR array."""
        h, w = image_bgr.shape[:2]
        page = LoadedPage(
            source_name=source_name,
            page_index=page_index,
            image_bgr=image_bgr,
            original_width=w,
            original_height=h,
        )
        return self.scan_page(page)

    def scan_bytes(
        self,
        data: bytes,
        filename: str,
        max_pages: int | None = None,
    ) -> list[tuple[SheetResult, np.ndarray | None]]:
        """Scan an uploaded image or multi-page PDF byte buffer."""
        pages = load_bytes(data, filename=filename, dpi=self.dpi, max_pages=max_pages)
        return [self.scan_page(page) for page in pages]

    def scan_file(
        self,
        path: str | Path,
        save_overlay_dir: str | Path | None = None,
    ) -> list[SheetResult]:
        """Scan all pages of an image or PDF file on disk."""
        file_path = Path(path)
        try:
            pages = load_document(file_path, dpi=self.dpi)
        except DocumentLoadError as exc:
            return [
                SheetResult(
                    sheet_id=file_path.stem,
                    source_file=file_path.name,
                    page_index=0,
                    template_name=self.template.name,
                    overall_confidence=0.0,
                    registration_method=self.template.registration.mode,
                    registration_score=0.0,
                    error=str(exc),
                )
            ]
        return [self.scan_page(p, save_overlay_dir=save_overlay_dir)[0] for p in pages]

    def scan_batch(
        self,
        input_path: str | Path | list[Path],
        workers: int | None = None,
        recursive: bool = False,
        save_overlay_dir: str | Path | None = None,
        progress_cb: Callable[[int, int, str], None] | None = None,
    ) -> BatchResult:
        """Scan a folder or list of files sequentially or with ProcessPoolExecutor."""
        files = (
            input_path
            if isinstance(input_path, list)
            else discover_documents(input_path, recursive=recursive)
        )

        # Exclude marker or reference assets referenced by the template itself
        excluded: set[Path] = set()
        if self.template.registration.marker_path:
            excluded.add(Path(self.template.registration.marker_path).resolve())
        if self.template.registration.reference_path:
            excluded.add(Path(self.template.registration.reference_path).resolve())
        files = [f for f in files if f.resolve() not in excluded]

        t0 = perf_counter()
        all_results: list[SheetResult] = []
        total_files = len(files)

        max_workers = workers if workers is not None else min(4, os.cpu_count() or 1)
        use_parallel = max_workers > 1 and total_files >= 4

        if use_parallel:
            template_dict = self.template.model_dump(mode="json")
            overlay_str = str(save_overlay_dir) if save_overlay_dir else None
            tasks = [(str(f), template_dict, self.dpi, overlay_str) for f in files]
            ordered: dict[int, list[SheetResult]] = {}

            with ProcessPoolExecutor(max_workers=max_workers) as pool:
                future_map = {
                    pool.submit(_scan_single_file_worker, task): idx
                    for idx, task in enumerate(tasks)
                }
                for completed, future in enumerate(as_completed(future_map), start=1):
                    idx = future_map[future]
                    raw_list = future.result()
                    ordered[idx] = [SheetResult.model_validate(item) for item in raw_list]
                    if progress_cb:
                        progress_cb(completed, total_files, files[idx].name)

            for idx in range(total_files):
                all_results.extend(ordered.get(idx, []))
        else:
            for idx, file_path in enumerate(files, start=1):
                results = self.scan_file(file_path, save_overlay_dir=save_overlay_dir)
                all_results.extend(results)
                if progress_cb:
                    progress_cb(idx, total_files, file_path.name)

        elapsed_ms = (perf_counter() - t0) * 1000.0
        ensure_unique_sheet_ids(all_results)
        succeeded = sum(1 for r in all_results if r.error is None)
        failed = sum(1 for r in all_results if r.error is not None)
        flagged = sum(1 for r in all_results if r.error is None and len(r.review_items) > 0)
        sheets_per_min = (
            (len(all_results) / (elapsed_ms / 60000.0)) if elapsed_ms > 0 and all_results else 0.0
        )

        return BatchResult(
            template_name=self.template.name,
            sheets=all_results,
            total_sheets=len(all_results),
            succeeded=succeeded,
            flagged_sheets=flagged,
            failed_sheets=failed,
            total_elapsed_ms=round(elapsed_ms, 2),
            sheets_per_minute=round(sheets_per_min, 1),
        )


def ensure_unique_sheet_ids(sheets: list[SheetResult]) -> list[SheetResult]:
    """Disambiguate duplicate sheet_ids within a batch (e.g., exam.jpg + exam.png)."""
    seen: dict[str, int] = {}
    for sheet in sheets:
        base = sheet.sheet_id
        count = seen.get(base, 0)
        if count > 0:
            candidate = f"{base}_{count + 1}"
            while candidate in seen:
                count += 1
                candidate = f"{base}_{count + 1}"
            sheet.sheet_id = candidate
            seen[candidate] = 1
            seen[base] = count + 1
        else:
            seen[base] = 1
    return sheets
