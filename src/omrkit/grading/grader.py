"""Flexible exam grader supporting multi-booklets, negative marking, and section rules."""

from __future__ import annotations

from omrkit.grading.analytics import compute_exam_analytics
from omrkit.models.grading import (
    AnswerKey,
    GradingPolicy,
    GradingReport,
    QuestionVerdict,
    SectionRule,
    SectionScore,
    StudentGrade,
    VerdictType,
)
from omrkit.models.scan import SheetResult
from omrkit.models.template import expand_field_labels


class ExamGrader:
    """Evaluates scanned OMR sheets against an AnswerKey and GradingPolicy."""

    def __init__(
        self,
        answer_key: AnswerKey,
        policy: GradingPolicy | None = None,
    ) -> None:
        self.answer_key = answer_key
        self.policy = policy or GradingPolicy()
        self._bonus_set = set(expand_field_labels(self.policy.bonus_questions))
        self._section_map: dict[str, SectionRule] = {}
        self._expanded_sections: list[tuple[SectionRule, list[str]]] = []

        for sec in self.policy.sections:
            q_list = expand_field_labels(sec.questions)
            self._expanded_sections.append((sec, q_list))
            for qid in q_list:
                self._section_map[qid] = sec

    def _rule_for_question(self, qid: str) -> tuple[float, float, float]:
        sec = self._section_map.get(qid)
        if sec is not None:
            return sec.correct_points, sec.incorrect_points, sec.blank_points
        return (
            self.policy.correct_points,
            self.policy.incorrect_points,
            self.policy.blank_points,
        )

    def grade_sheet(self, sheet: SheetResult) -> StudentGrade:
        """Grade one scanned optical sheet and produce a full StudentGrade scorecard."""
        flat = sheet.flat_responses()
        booklet = self.answer_key.default_booklet
        if self.answer_key.booklet_field:
            candidate = flat.get(self.answer_key.booklet_field, "").strip()
            if candidate:
                booklet = candidate

        expected_map = self.answer_key.resolve_booklet(booklet)
        verdicts: list[QuestionVerdict] = []

        correct_cnt = 0
        incorrect_cnt = 0
        blank_cnt = 0
        bonus_cnt = 0
        raw_score = 0.0
        max_score = 0.0

        for qid, expected_raw in expected_map.items():
            c_pts, i_pts, b_pts = self._rule_for_question(qid)
            max_score += c_pts

            field_reading = sheet.fields.get(qid)
            marked = field_reading.value.strip() if field_reading else flat.get(qid, "").strip()
            conf = field_reading.confidence if field_reading else 1.0

            acceptable = (
                [opt.strip() for opt in expected_raw]
                if isinstance(expected_raw, list)
                else [str(expected_raw).strip()]
            )
            expected_display = "/".join(acceptable)

            verdict: VerdictType
            points: float

            if qid in self._bonus_set:
                verdict = "bonus"
                points = c_pts
                bonus_cnt += 1
            elif marked == "":
                verdict = "blank"
                points = b_pts
                blank_cnt += 1
            elif marked in acceptable:
                verdict = "correct"
                points = c_pts
                correct_cnt += 1
            elif (
                self.policy.partial_credit
                and len(marked) > 1
                and any(ch in acceptable for ch in marked)
            ):
                verdict = "correct"
                points = round(c_pts / float(len(marked)), 4)
                correct_cnt += 1
            else:
                verdict = "incorrect"
                points = i_pts
                incorrect_cnt += 1

            raw_score += points
            verdicts.append(
                QuestionVerdict(
                    question_id=qid,
                    marked=marked,
                    expected=expected_display,
                    verdict=verdict,
                    points=round(points, 4),
                    confidence=conf,
                )
            )

        # Compute per-section subtotals when section rules are configured
        verdict_by_q = {v.question_id: v for v in verdicts}
        sections_out: list[SectionScore] = []
        for sec, q_list in self._expanded_sections:
            s_correct = 0
            s_incorrect = 0
            s_blank = 0
            s_score = 0.0
            s_max = 0.0
            for qid in q_list:
                if qid not in verdict_by_q:
                    continue
                v = verdict_by_q[qid]
                s_max += sec.correct_points
                s_score += v.points
                if v.verdict in {"correct", "bonus"}:
                    s_correct += 1
                elif v.verdict == "blank":
                    s_blank += 1
                else:
                    s_incorrect += 1
            sections_out.append(
                SectionScore(
                    name=sec.name,
                    correct=s_correct,
                    incorrect=s_incorrect,
                    blank=s_blank,
                    score=round(s_score, 2),
                    max_score=round(s_max, 2),
                )
            )

        percentage = max(0.0, (raw_score / max_score) * 100.0) if max_score > 0 else 0.0

        # Preserve student identity metadata (grouped fields + booklet)
        student_meta = dict(sheet.grouped_values)
        if self.answer_key.booklet_field:
            student_meta[self.answer_key.booklet_field] = booklet

        return StudentGrade(
            sheet_id=sheet.sheet_id,
            source_file=sheet.source_file,
            student_metadata=student_meta,
            booklet=booklet,
            total_questions=len(expected_map),
            correct=correct_cnt,
            incorrect=incorrect_cnt,
            blank=blank_cnt,
            bonus=bonus_cnt,
            raw_score=round(raw_score, 2),
            max_score=round(max_score, 2),
            percentage=round(percentage, 2),
            flagged_for_review=len(sheet.review_items) > 0,
            sections=sections_out,
            verdicts=verdicts,
        )

    def grade_batch(self, sheets: list[SheetResult]) -> GradingReport:
        """Grade all valid sheets and produce cohort-level psychometric analytics."""
        valid_sheets = [s for s in sheets if s.error is None]
        grades = [self.grade_sheet(s) for s in valid_sheets]
        analytics = compute_exam_analytics(grades, self.answer_key)
        return GradingReport(
            exam_name=self.answer_key.exam_name,
            policy_name=self.policy.name,
            grades=grades,
            analytics=analytics,
        )
