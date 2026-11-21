"""Vector PDF optical sheet generator with ArUco anchors and zero-calibration Template output."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from omrkit._version import __version__
from omrkit.generator.presets import SheetSpec
from omrkit.io.pdf_fonts import get_pdf_fonts
from omrkit.models.grading import AnswerKey
from omrkit.models.template import (
    DetectionConfig,
    FieldBlock,
    RegistrationConfig,
    Template,
)
from omrkit.vision.qr import encode_sheet_qr_payload, render_qr_matrix

_MM_TO_PT = 72.0 / 25.4
_PAGE_DIMENSIONS_MM: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "LETTER": (215.9, 279.4),
}


@dataclass(slots=True)
class GeneratedSheet:
    """Paired printable PDF bytes, pixel-exact Template, and sample AnswerKey."""

    pdf_bytes: bytes
    template: Template
    sample_answer_key: AnswerKey


def _aruco_image_reader(marker_id: int, pixel_size: int = 240) -> ImageReader:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker_img = cv2.aruco.generateImageMarker(dictionary, marker_id, pixel_size)
    # Add crisp 1-module white quiet zone around the black border
    pad = pixel_size // 8
    padded = cv2.copyMakeBorder(marker_img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    pil_img = Image.fromarray(padded).convert("L")
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def _qr_image_reader(preset_id: str, pixel_size: int = 220) -> ImageReader:
    payload = encode_sheet_qr_payload(preset_id)
    qr_img = render_qr_matrix(payload, pixel_size=pixel_size)
    pil_img = Image.fromarray(qr_img).convert("L")
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


class SheetGenerator:
    """Generates print-ready vector PDF OMR sheets alongside mathematically exact Templates."""

    def generate(self, spec: SheetSpec) -> GeneratedSheet:
        """Render the PDF in memory and construct its zero-calibration Template."""
        fonts = get_pdf_fonts()
        page_w_mm, page_h_mm = _PAGE_DIMENSIONS_MM[spec.page_format]
        dpi = spec.dpi
        mm_to_px = dpi / 25.4
        page_w_px = round(page_w_mm * mm_to_px)
        page_h_px = round(page_h_mm * mm_to_px)
        page_w_pt = page_w_mm * _MM_TO_PT
        page_h_pt = page_h_mm * _MM_TO_PT

        buf = io.BytesIO()
        pdf = rl_canvas.Canvas(buf, pagesize=(page_w_pt, page_h_pt))
        pdf.setTitle(fonts.format_text(spec.title))
        pdf.setAuthor(f"OMRKit v{__version__}")

        def x_pt(x_mm: float) -> float:
            return x_mm * _MM_TO_PT

        def y_pt(y_mm_top: float) -> float:
            return page_h_pt - (y_mm_top * _MM_TO_PT)

        # 1. Draw 4 ArUco corner markers (IDs 0=TL, 1=TR, 2=BR, 3=BL)
        marker_draw_mm = 15.0  # includes quiet zone
        margin_mm = 13.5
        corner_centers_mm = [
            (margin_mm, margin_mm),  # TL (ID 0)
            (page_w_mm - margin_mm, margin_mm),  # TR (ID 1)
            (page_w_mm - margin_mm, page_h_mm - margin_mm),  # BR (ID 2)
            (margin_mm, page_h_mm - margin_mm),  # BL (ID 3)
        ]
        for marker_id, (mx, my) in enumerate(corner_centers_mm):
            reader = _aruco_image_reader(marker_id)
            half = marker_draw_mm / 2.0
            pdf.drawImage(
                reader,
                x_pt(mx - half),
                y_pt(my + half),
                width=marker_draw_mm * _MM_TO_PT,
                height=marker_draw_mm * _MM_TO_PT,
                preserveAspectRatio=True,
                mask=None,
            )

        target_corners_px = [
            (round(mx * mm_to_px, 2), round(my * mm_to_px, 2)) for mx, my in corner_centers_mm
        ]

        # 2. Header band
        ink = colors.HexColor("#18202A")
        muted = colors.HexColor("#5C6773")
        border = colors.HexColor("#CBD3DC")
        header_bg = colors.HexColor("#F4F6F8")

        pdf.setFillColor(ink)
        pdf.setFont(fonts.bold, 13.5)
        pdf.drawCentredString(page_w_pt / 2.0, y_pt(13.0), fonts.format_text(spec.title))
        pdf.setFillColor(muted)
        pdf.setFont(fonts.regular, 8.5)
        pdf.drawCentredString(page_w_pt / 2.0, y_pt(18.5), fonts.format_text(spec.subtitle))

        # Name / Date box + embedded auto-detect QR template identifier
        qr_size_mm = 15.0
        qr_left_mm = page_w_mm - 41.0
        qr_top_mm = 20.0
        pdf.drawImage(
            _qr_image_reader(spec.preset_id),
            x_pt(qr_left_mm),
            y_pt(qr_top_mm + qr_size_mm),
            width=qr_size_mm * _MM_TO_PT,
            height=qr_size_mm * _MM_TO_PT,
            preserveAspectRatio=True,
            mask=None,
        )

        box_left = 26.0
        box_right = qr_left_mm - 3.0
        pdf.setStrokeColor(border)
        pdf.setLineWidth(0.7)
        pdf.roundRect(
            x_pt(box_left),
            y_pt(32.0),
            (box_right - box_left) * _MM_TO_PT,
            9.5 * _MM_TO_PT,
            2.0,
            stroke=1,
            fill=0,
        )
        pdf.setFillColor(muted)
        pdf.setFont(fonts.bold, 7.5)
        pdf.drawString(x_pt(box_left + 3.0), y_pt(28.5), "NAME / SURNAME:")
        pdf.drawString(x_pt(box_right - 44.0), y_pt(28.5), "DATE:")

        blocks: list[FieldBlock] = []
        content_left = 18.0
        content_right = page_w_mm - 18.0
        content_w = content_right - content_left

        # 3. Optional Top Row: ID Grids + Booklet selector
        id_row_top = 37.5
        id_bubble_r_mm = 2.0
        id_bubbles_gap_mm = 5.4
        id_labels_gap_mm = 5.6
        cursor_x = content_left
        id_section_bottom = id_row_top

        for grid in spec.id_grids:
            grid_w = (grid.digits - 1) * id_labels_gap_mm + 10.0
            grid_h = 11.0 + (len(grid.options) - 1) * id_bubbles_gap_mm + 6.5

            # Card container
            pdf.setFillColor(header_bg)
            pdf.setStrokeColor(border)
            pdf.setLineWidth(0.6)
            pdf.rect(
                x_pt(cursor_x),
                y_pt(id_row_top + 6.2),
                grid_w * _MM_TO_PT,
                6.2 * _MM_TO_PT,
                stroke=1,
                fill=1,
            )
            pdf.setFillColor(ink)
            pdf.setFont(fonts.bold, 7.5)
            pdf.drawCentredString(
                x_pt(cursor_x + grid_w / 2.0),
                y_pt(id_row_top + 4.3),
                fonts.format_text(grid.title.upper()),
            )

            # Outer grid frame
            pdf.rect(
                x_pt(cursor_x),
                y_pt(id_row_top + grid_h),
                grid_w * _MM_TO_PT,
                (grid_h - 6.2) * _MM_TO_PT,
                stroke=1,
                fill=0,
            )

            first_cx = cursor_x + 5.0
            first_cy = id_row_top + 11.5

            # Write digit box row headers
            for d_idx in range(grid.digits):
                cx_mm = first_cx + d_idx * id_labels_gap_mm
                pdf.setStrokeColor(border)
                pdf.rect(
                    x_pt(cx_mm - 2.3),
                    y_pt(id_row_top + 9.4),
                    4.6 * _MM_TO_PT,
                    3.2 * _MM_TO_PT,
                    stroke=1,
                    fill=0,
                )
                for opt_idx, opt in enumerate(grid.options):
                    cy_mm = first_cy + opt_idx * id_bubbles_gap_mm
                    self._draw_bubble(
                        pdf,
                        x_pt(cx_mm),
                        y_pt(cy_mm),
                        id_bubble_r_mm * _MM_TO_PT,
                        opt,
                        fonts.regular,
                    )

            prefix = grid.name.lower()
            blocks.append(
                FieldBlock(
                    name=f"ID_{grid.name}",
                    field_type="grid_digits",
                    direction="vertical",
                    origin=(round(first_cx * mm_to_px, 2), round(first_cy * mm_to_px, 2)),
                    origin_mode="center",
                    bubble_radius=round(id_bubble_r_mm * mm_to_px, 2),
                    bubbles_gap=round(id_bubbles_gap_mm * mm_to_px, 2),
                    labels_gap=round(id_labels_gap_mm * mm_to_px, 2),
                    options=list(grid.options),
                    labels=[f"{prefix}_1..{grid.digits}"],
                    group_as=grid.name,
                    validator=grid.validator,
                )
            )

            cursor_x += grid_w + 5.0
            id_section_bottom = max(id_section_bottom, id_row_top + grid_h)

        if spec.include_booklet:
            bk_w = max(32.0, (len(spec.booklet_options) - 1) * 7.5 + 14.0)
            bk_h = 20.0
            # Place booklet card right-aligned in the ID band if space permits
            bk_x = max(cursor_x, content_right - bk_w)
            pdf.setFillColor(header_bg)
            pdf.setStrokeColor(border)
            pdf.setLineWidth(0.6)
            pdf.rect(
                x_pt(bk_x),
                y_pt(id_row_top + 6.2),
                bk_w * _MM_TO_PT,
                6.2 * _MM_TO_PT,
                stroke=1,
                fill=1,
            )
            pdf.setFillColor(ink)
            pdf.setFont(fonts.bold, 7.5)
            pdf.drawCentredString(x_pt(bk_x + bk_w / 2.0), y_pt(id_row_top + 4.3), "BOOKLET")
            pdf.rect(
                x_pt(bk_x),
                y_pt(id_row_top + bk_h),
                bk_w * _MM_TO_PT,
                (bk_h - 6.2) * _MM_TO_PT,
                stroke=1,
                fill=0,
            )

            bk_gap = 7.2
            bk_r = 2.2
            bk_first_cx = bk_x + (bk_w - (len(spec.booklet_options) - 1) * bk_gap) / 2.0
            bk_cy = id_row_top + 13.5
            for opt_idx, opt in enumerate(spec.booklet_options):
                self._draw_bubble(
                    pdf,
                    x_pt(bk_first_cx + opt_idx * bk_gap),
                    y_pt(bk_cy),
                    bk_r * _MM_TO_PT,
                    opt,
                    fonts.regular,
                )

            blocks.append(
                FieldBlock(
                    name="BOOKLET_BLOCK",
                    field_type="custom",
                    direction="horizontal",
                    origin=(round(bk_first_cx * mm_to_px, 2), round(bk_cy * mm_to_px, 2)),
                    origin_mode="center",
                    bubble_radius=round(bk_r * mm_to_px, 2),
                    bubbles_gap=round(bk_gap * mm_to_px, 2),
                    labels_gap=round(7.0 * mm_to_px, 2),
                    options=list(spec.booklet_options),
                    labels=["BOOKLET"],
                )
            )
            id_section_bottom = max(id_section_bottom, id_row_top + bk_h)

        # 4. Multi-column MCQ Answer Grid
        answers_top = id_section_bottom + 7.5
        answers_bottom_limit = page_h_mm - 26.5
        avail_h = answers_bottom_limit - answers_top

        num_cols = math.ceil(spec.num_questions / spec.questions_per_column)
        col_gap_mm = 4.5
        col_w_mm = (content_w - (num_cols - 1) * col_gap_mm) / num_cols

        # Dynamically adapt row spacing and bubble sizing to fit cleanly within A4/Letter height
        max_rows = min(spec.questions_per_column, spec.num_questions)
        header_h_mm = 7.0
        row_pitch_mm = min(6.2, max(4.7, (avail_h - header_h_mm - 3.0) / max_rows))
        num_opts = len(spec.options)
        # Space for question number label + options
        q_label_pad_mm = 8.5
        opt_gap_mm = min(6.8, max(4.6, (col_w_mm - q_label_pad_mm - 4.0) / max(1, num_opts - 1)))
        bubble_r_mm = min(2.15, max(1.65, min(row_pitch_mm, opt_gap_mm) * 0.36))

        sample_answers: dict[str, str | list[str]] = {}

        for col_idx in range(num_cols):
            q_start = col_idx * spec.questions_per_column + 1
            q_end = min(spec.num_questions, q_start + spec.questions_per_column - 1)
            row_count = q_end - q_start + 1

            col_x = content_left + col_idx * (col_w_mm + col_gap_mm)
            col_h = header_h_mm + row_count * row_pitch_mm + 2.0

            # Column header
            pdf.setFillColor(header_bg)
            pdf.setStrokeColor(border)
            pdf.setLineWidth(0.6)
            pdf.rect(
                x_pt(col_x),
                y_pt(answers_top + header_h_mm),
                col_w_mm * _MM_TO_PT,
                header_h_mm * _MM_TO_PT,
                stroke=1,
                fill=1,
            )
            pdf.setFillColor(ink)
            pdf.setFont(fonts.bold, 7.2)
            pdf.drawCentredString(
                x_pt(col_x + col_w_mm / 2.0),
                y_pt(answers_top + 4.7),
                f"QUESTIONS {q_start} - {q_end}",
            )

            # Column body frame
            pdf.rect(
                x_pt(col_x),
                y_pt(answers_top + col_h),
                col_w_mm * _MM_TO_PT,
                (col_h - header_h_mm) * _MM_TO_PT,
                stroke=1,
                fill=0,
            )

            first_bubble_x = col_x + q_label_pad_mm + 1.5
            first_bubble_y = answers_top + header_h_mm + row_pitch_mm * 0.65

            for r_idx in range(row_count):
                q_num = q_start + r_idx
                cy_mm = first_bubble_y + r_idx * row_pitch_mm

                # Alternating subtle row shading for human readability
                if r_idx % 2 == 1:
                    pdf.setFillColor(colors.HexColor("#FAFBFD"))
                    pdf.rect(
                        x_pt(col_x + 0.4),
                        y_pt(cy_mm + row_pitch_mm * 0.48),
                        (col_w_mm - 0.8) * _MM_TO_PT,
                        (row_pitch_mm * 0.96) * _MM_TO_PT,
                        stroke=0,
                        fill=1,
                    )

                pdf.setFillColor(ink)
                pdf.setFont(fonts.bold, 7.0)
                pdf.drawRightString(
                    x_pt(col_x + q_label_pad_mm - 1.4),
                    y_pt(cy_mm + 0.9),
                    str(q_num),
                )

                for opt_idx, opt in enumerate(spec.options):
                    cx_mm = first_bubble_x + opt_idx * opt_gap_mm
                    self._draw_bubble(
                        pdf, x_pt(cx_mm), y_pt(cy_mm), bubble_r_mm * _MM_TO_PT, opt, fonts.regular
                    )

                sample_answers[f"{spec.question_prefix}{q_num}"] = spec.options[
                    (q_num - 1) % len(spec.options)
                ]

            blocks.append(
                FieldBlock(
                    name=f"MCQ_COL_{col_idx + 1}",
                    field_type="mcq",
                    direction="horizontal",
                    origin=(
                        round(first_bubble_x * mm_to_px, 2),
                        round(first_bubble_y * mm_to_px, 2),
                    ),
                    origin_mode="center",
                    bubble_radius=round(bubble_r_mm * mm_to_px, 2),
                    bubbles_gap=round(opt_gap_mm * mm_to_px, 2),
                    labels_gap=round(row_pitch_mm * mm_to_px, 2),
                    options=list(spec.options),
                    labels=[f"{spec.question_prefix}{q_start}..{q_end}"],
                )
            )

        # Footer note
        pdf.setFillColor(muted)
        pdf.setFont(fonts.regular, 7.0)
        pdf.drawCentredString(
            page_w_pt / 2.0,
            y_pt(page_h_mm - 11.5),
            f"OMRKit v{__version__} | Preset: {spec.preset_id} | ArUco DICT_4X4_50 [0,1,2,3] | {page_w_px}x{page_h_px}@{dpi}DPI",
        )

        pdf.showPage()
        pdf.save()

        template = Template(
            version="2.0",
            name=spec.preset_id,
            description=spec.title,
            page_width=page_w_px,
            page_height=page_h_px,
            registration=RegistrationConfig(
                mode="aruco",
                aruco_dict="DICT_4X4_50",
                aruco_ids=(0, 1, 2, 3),
                target_corners=target_corners_px,
            ),
            detection=DetectionConfig(),
            blocks=blocks,
            metadata={
                "generated_by": "omrkit.SheetGenerator",
                "page_format": spec.page_format,
                "dpi": dpi,
                "num_questions": spec.num_questions,
            },
        )

        answer_key = AnswerKey(
            exam_name=spec.title,
            booklet_field="BOOKLET" if spec.include_booklet else None,
            default_booklet="A",
            answers=sample_answers,
        )

        return GeneratedSheet(
            pdf_bytes=buf.getvalue(),
            template=template,
            sample_answer_key=answer_key,
        )

    @staticmethod
    def _draw_bubble(
        pdf: rl_canvas.Canvas,
        cx_pt: float,
        cy_pt: float,
        radius_pt: float,
        label: str,
        font_name: str = "Helvetica",
    ) -> None:
        """Draw a clean light-outlined circular bubble with a soft interior letter."""
        pdf.setStrokeColor(colors.HexColor("#7B8794"))
        pdf.setLineWidth(0.65)
        pdf.setFillColor(colors.white)
        pdf.circle(cx_pt, cy_pt, radius_pt, stroke=1, fill=1)

        pdf.setFillColor(colors.HexColor("#B8C2CC"))
        font_size = max(4.8, radius_pt * 1.05)
        pdf.setFont(font_name, font_size)
        pdf.drawCentredString(cx_pt, cy_pt - font_size * 0.34, label)

    def generate_to_dir(self, spec: SheetSpec, output_dir: str | Path) -> dict[str, Path]:
        """Write sheet.pdf, template.json, and sample_answer_key.json into output_dir."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        generated = self.generate(spec)

        pdf_path = out / f"{spec.preset_id}_sheet.pdf"
        template_path = out / "template.json"
        key_path = out / "answer_key.json"

        pdf_path.write_bytes(generated.pdf_bytes)
        generated.template.to_file(template_path)
        generated.sample_answer_key.to_file(key_path)

        return {
            "pdf": pdf_path,
            "template": template_path,
            "answer_key": key_path,
        }
