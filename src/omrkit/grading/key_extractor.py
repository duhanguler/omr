"""Zero-JSON AnswerKey extraction directly from scanned teacher answer-key sheets."""

from __future__ import annotations

from pydantic import BaseModel, Field

from omrkit.models.grading import AnswerKey
from omrkit.models.scan import SheetResult
from omrkit.models.template import Template


class ExtractedKeyResult(BaseModel):
    """Structured output returned when extracting an AnswerKey from teacher key sheet(s)."""

    answer_key: AnswerKey
    booklets_detected: list[str] = Field(default_factory=list)
    questions_count: int = 0
    blank_questions: list[str] = Field(default_factory=list)
    multi_answer_questions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _select_question_ids(
    sheet: SheetResult, template: Template | None, booklet_field: str | None
) -> list[str]:
    """Identify ordered MCQ question field IDs from a scanned sheet."""
    if template is not None:
        mcq_ids = [
            lbl
            for blk in template.blocks
            if blk.field_type == "mcq"
            for lbl in blk.expanded_labels()
        ]
        if mcq_ids:
            return [qid for qid in mcq_ids if qid in sheet.fields]

    # Heuristic fallback when template isn't passed: exclude grouped ID sub-fields and booklet
    grouped_prefixes = tuple(f"{g.lower()}_" for g in sheet.grouped_values)
    excluded = {booklet_field} if booklet_field else set()
    out: list[str] = []
    for fid in sheet.fields:
        if fid in excluded:
            continue
        lower = fid.lower()
        if any(lower.startswith(pref) for pref in grouped_prefixes):
            continue
        out.append(fid)
    return out


def extract_answer_key_from_sheets(
    sheets: list[SheetResult],
    *,
    template: Template | None = None,
    exam_name: str = "Scanned Answer Key",
    booklet_field: str | None = "BOOKLET",
) -> ExtractedKeyResult:
    """Build a single- or multi-booklet AnswerKey directly from scanned teacher key sheets.

    - Supports single-sheet keys (stored in ``AnswerKey.answers``) and multi-booklet keys
      (stored in ``AnswerKey.booklets`` keyed by the marked ``BOOKLET`` option).
    - Automatically converts questions where the teacher marked multiple bubbles (e.g. ``A`` and
      ``C``) into multi-answer entries (``["A", "C"]``).
    - Collects warnings for blank questions or duplicate booklet pages.
    """
    valid_sheets = [s for s in sheets if s.error is None]
    if not valid_sheets:
        raise ValueError("No valid scanned key sheets were provided.")

    per_sheet_maps: list[tuple[str, dict[str, str | list[str]]]] = []
    blank_questions: list[str] = []
    multi_answer_questions: list[str] = []
    warnings: list[str] = []
    has_booklet_field = False

    for idx, sheet in enumerate(valid_sheets):
        flat = sheet.flat_responses()
        detected_booklet = ""
        if booklet_field and booklet_field in flat:
            has_booklet_field = True
            detected_booklet = flat[booklet_field].strip().upper()
            if len(detected_booklet) > 1:
                warnings.append(
                    f"Booklet field on key sheet '{sheet.sheet_id}' had multiple marks ('{detected_booklet}'); "
                    f"using '{detected_booklet[0]}'."
                )
                detected_booklet = detected_booklet[0]
        if not detected_booklet:
            detected_booklet = chr(ord("A") + idx) if len(valid_sheets) > 1 else "A"

        qids = _select_question_ids(sheet, template, booklet_field)
        if not qids:
            raise ValueError(f"Sheet '{sheet.sheet_id}' contains no recognizable question fields.")

        answers_map: dict[str, str | list[str]] = {}
        marked_on_sheet = 0
        for qid in qids:
            reading = sheet.fields[qid]
            selected = [opt.strip() for opt in reading.selected_options if opt.strip()]
            if not selected:
                raw_val = reading.value.strip()
                if raw_val:
                    selected = [raw_val]

            if not selected:
                blank_questions.append(
                    f"{detected_booklet}:{qid}" if len(valid_sheets) > 1 else qid
                )
                answers_map[qid] = ""
            elif len(selected) == 1:
                marked_on_sheet += 1
                answers_map[qid] = selected[0]
            else:
                marked_on_sheet += 1
                multi_answer_questions.append(
                    f"{detected_booklet}:{qid}" if len(valid_sheets) > 1 else qid
                )
                answers_map[qid] = selected

        if marked_on_sheet == 0:
            raise ValueError(
                f"No marked answers were detected on key sheet '{sheet.sheet_id}'. "
                "Fill in the correct bubbles before scanning as an answer key."
            )

        per_sheet_maps.append((detected_booklet, answers_map))

    if blank_questions:
        preview = ", ".join(blank_questions[:8])
        suffix = f" (+{len(blank_questions) - 8} more)" if len(blank_questions) > 8 else ""
        warnings.append(f"Blank questions detected on key sheet: {preview}{suffix}.")

    if multi_answer_questions:
        preview = ", ".join(multi_answer_questions[:8])
        warnings.append(f"Multi-answer questions (any marked option accepted): {preview}.")

    if len(per_sheet_maps) == 1:
        bk_code, single_map = per_sheet_maps[0]
        key = AnswerKey(
            exam_name=exam_name,
            booklet_field=booklet_field if has_booklet_field else None,
            default_booklet=bk_code,
            answers=single_map,
        )
        return ExtractedKeyResult(
            answer_key=key,
            booklets_detected=[bk_code],
            questions_count=len(single_map),
            blank_questions=blank_questions,
            multi_answer_questions=multi_answer_questions,
            warnings=warnings,
        )

    booklets: dict[str, dict[str, str | list[str]]] = {}
    booklets_detected: list[str] = []
    for bk_code, qmap in per_sheet_maps:
        if bk_code in booklets:
            warnings.append(
                f"Duplicate booklet '{bk_code}' encountered; later sheet overwrote earlier one."
            )
        else:
            booklets_detected.append(bk_code)
        booklets[bk_code] = qmap

    default_bk = booklets_detected[0]
    key = AnswerKey(
        exam_name=exam_name,
        booklet_field=booklet_field or "BOOKLET",
        default_booklet=default_bk,
        booklets=booklets,
    )
    return ExtractedKeyResult(
        answer_key=key,
        booklets_detected=booklets_detected,
        questions_count=len(booklets[default_bk]),
        blank_questions=blank_questions,
        multi_answer_questions=multi_answer_questions,
        warnings=warnings,
    )
