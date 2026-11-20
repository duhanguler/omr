"""Classical Test Theory (CTT) psychometric analytics for graded exams."""

from __future__ import annotations

import math

import numpy as np

from omrkit.models.grading import (
    AnswerKey,
    ExamAnalytics,
    ItemPsychometrics,
    ScoreHistogramBin,
    StudentGrade,
)


def compute_exam_analytics(
    grades: list[StudentGrade],
    answer_key: AnswerKey,
) -> ExamAnalytics:
    """Compute score distribution, item difficulty (p), discrimination (D), and KR-20 reliability."""
    question_ids = answer_key.question_ids()
    default_answers = answer_key.resolve_booklet(answer_key.default_booklet)

    if not grades:
        return ExamAnalytics(
            student_count=0,
            question_count=len(question_ids),
            mean_score=0.0,
            median_score=0.0,
            std_score=0.0,
            min_score=0.0,
            max_score=0.0,
            mean_percentage=0.0,
            percentiles={},
            kr20_reliability=None,
            histogram=[],
            items=[],
        )

    scores = np.asarray([g.raw_score for g in grades], dtype=np.float64)
    pcts = np.asarray([g.percentage for g in grades], dtype=np.float64)
    n_students = len(grades)

    percentiles = {
        "p10": round(float(np.percentile(scores, 10)), 2),
        "p25": round(float(np.percentile(scores, 25)), 2),
        "p50": round(float(np.percentile(scores, 50)), 2),
        "p75": round(float(np.percentile(scores, 75)), 2),
        "p90": round(float(np.percentile(scores, 90)), 2),
    }

    # Build 10-bin percentage histogram (0-10, 10-20, ..., 90-100)
    histogram: list[ScoreHistogramBin] = []
    for idx in range(10):
        lo = idx * 10.0
        hi = (idx + 1) * 10.0
        if idx == 9:
            count = int(np.sum((pcts >= lo) & (pcts <= hi)))
        else:
            count = int(np.sum((pcts >= lo) & (pcts < hi)))
        histogram.append(
            ScoreHistogramBin(
                label=f"{int(lo)}-{int(hi)}%",
                low=lo,
                high=hi,
                count=count,
            )
        )

    # Sort students by total score for upper/lower 27% discrimination index
    sorted_grades = sorted(grades, key=lambda g: g.raw_score, reverse=True)
    group_n = max(1, round(n_students * 0.27))
    upper_group = sorted_grades[:group_n]
    lower_group = sorted_grades[-group_n:]

    verdict_lookup = [{v.question_id: v for v in g.verdicts} for g in grades]
    upper_lookup = [{v.question_id: v for v in g.verdicts} for g in upper_group]
    lower_lookup = [{v.question_id: v for v in g.verdicts} for g in lower_group]

    items: list[ItemPsychometrics] = []
    sum_pq = 0.0
    binary_totals = np.zeros(n_students, dtype=np.float64)

    for qid in question_ids:
        expected_raw = default_answers.get(qid, "")
        expected_str = (
            "/".join(expected_raw) if isinstance(expected_raw, list) else str(expected_raw)
        )

        correct_c = 0
        incorrect_c = 0
        blank_c = 0
        option_dist: dict[str, int] = {}

        for s_idx, vmap in enumerate(verdict_lookup):
            v = vmap.get(qid)
            if v is None:
                blank_c += 1
                option_dist["BLANK"] = option_dist.get("BLANK", 0) + 1
                continue

            key_opt = v.marked if v.marked else "BLANK"
            option_dist[key_opt] = option_dist.get(key_opt, 0) + 1

            if v.verdict in {"correct", "bonus"}:
                correct_c += 1
                binary_totals[s_idx] += 1.0
            elif v.verdict == "blank":
                blank_c += 1
            else:
                incorrect_c += 1

        p_val = correct_c / float(n_students)
        sum_pq += p_val * (1.0 - p_val)
        omit_rate = blank_c / float(n_students)

        if n_students >= 2:
            upper_correct = sum(
                1 for vm in upper_lookup if qid in vm and vm[qid].verdict in {"correct", "bonus"}
            )
            lower_correct = sum(
                1 for vm in lower_lookup if qid in vm and vm[qid].verdict in {"correct", "bonus"}
            )
            disc_d = (upper_correct - lower_correct) / float(group_n)
        else:
            disc_d = 0.0

        quality_flag: str = "good"
        if n_students >= 4 and disc_d < 0.15:
            quality_flag = "poor_discrimination"
        elif p_val > 0.90:
            quality_flag = "too_easy"
        elif p_val < 0.25:
            quality_flag = "too_hard"

        items.append(
            ItemPsychometrics(
                question_id=qid,
                expected=expected_str,
                attempts=n_students,
                correct_count=correct_c,
                incorrect_count=incorrect_c,
                blank_count=blank_c,
                difficulty_p=round(p_val, 4),
                discrimination_d=round(float(np.clip(disc_d, -1.0, 1.0)), 4),
                omit_rate=round(omit_rate, 4),
                option_distribution=dict(sorted(option_dist.items())),
                quality_flag=quality_flag,  # type: ignore[arg-type]
            )
        )

    # Kuder-Richardson Formula 20 (KR-20) internal consistency reliability
    kr20: float | None = None
    k = len(question_ids)
    if k >= 2 and n_students >= 2:
        total_var = float(np.var(binary_totals, ddof=1))
        if total_var > 1e-9:
            raw_kr20 = (k / float(k - 1)) * (1.0 - (sum_pq / total_var))
            if not math.isnan(raw_kr20):
                kr20 = round(float(np.clip(raw_kr20, -1.0, 1.0)), 4)

    return ExamAnalytics(
        student_count=n_students,
        question_count=k,
        mean_score=round(float(np.mean(scores)), 2),
        median_score=round(float(np.median(scores)), 2),
        std_score=round(float(np.std(scores, ddof=0)), 2),
        min_score=round(float(np.min(scores)), 2),
        max_score=round(float(np.max(scores)), 2),
        mean_percentage=round(float(np.mean(pcts)), 2),
        percentiles=percentiles,
        kr20_reliability=kr20,
        histogram=histogram,
        items=items,
    )
