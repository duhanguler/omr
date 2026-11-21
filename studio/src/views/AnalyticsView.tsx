import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Award,
  Download,
  FileSpreadsheet,
  FileText,
  Play,
} from "lucide-react";
import {
  exportReportFile,
  exportStudentScorecard,
  gradeSheets,
  triggerBlobDownload,
} from "../api/client";
import type { Dictionary } from "../i18n";
import type {
  AnswerKey,
  GradingPolicy,
  GradingReport,
  SheetResult,
  StudentGrade,
} from "../types";

interface AnalyticsViewProps {
  t: Dictionary;
  sheets: SheetResult[];
  policies: GradingPolicy[];
  answerKey: AnswerKey | null;
  onUpdateAnswerKey: (key: AnswerKey) => void;
  report: GradingReport | null;
  onReportReady: (report: GradingReport) => void;
}

type SortKey = "sheet_id" | "raw_score" | "percentage";
type ItemFilter = "all" | "poor_discrimination" | "too_hard" | "too_easy";

export function AnalyticsView({
  t,
  sheets,
  policies,
  answerKey,
  onUpdateAnswerKey,
  report,
  onReportReady,
}: AnalyticsViewProps) {
  const [selectedPolicyName, setSelectedPolicyName] = useState<string>(
    report?.policy_name ?? "standard"
  );
  const [selectedBooklet, setSelectedBooklet] = useState<string>("A");
  const [hoveredBinIdx, setHoveredBinIdx] = useState<number | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("percentage");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [itemFilter, setItemFilter] = useState<ItemFilter>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (report?.policy_name) {
      setSelectedPolicyName(report.policy_name);
    }
  }, [report?.policy_name]);

  const bookletNames = answerKey ? Object.keys(answerKey.booklets ?? {}) : [];
  const hasBooklets = bookletNames.length > 0;
  const activeBooklet = hasBooklets
    ? bookletNames.includes(selectedBooklet)
      ? selectedBooklet
      : answerKey?.default_booklet && bookletNames.includes(answerKey.default_booklet)
        ? answerKey.default_booklet
        : bookletNames[0]
    : "";

  const policy =
    policies.find((p) => p.name === selectedPolicyName) ?? {
      name: "standard",
      correct_points: 1,
      incorrect_points: 0,
      blank_points: 0,
      partial_credit: false,
      bonus_questions: [],
      sections: [],
    };

  const activeAnswersMap = answerKey
    ? hasBooklets
      ? answerKey.booklets[activeBooklet] ?? {}
      : answerKey.answers ?? {}
    : {};
  const answersEntries = Object.entries(activeAnswersMap);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "sheet_id" ? "asc" : "desc");
    }
  }

  const sortedGrades = useMemo(() => {
    if (!report) return [];
    const copy = [...report.grades];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "sheet_id") {
        cmp = a.sheet_id.localeCompare(b.sheet_id, undefined, { numeric: true });
      } else if (sortKey === "raw_score") {
        cmp = a.raw_score - b.raw_score;
      } else {
        cmp = a.percentage - b.percentage;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [report, sortKey, sortDir]);

  const analytics = report?.analytics;
  const maxBin = Math.max(1, ...(analytics?.histogram.map((b) => b.count) ?? [1]));
  const totalStudents = analytics?.student_count ?? 0;
  const hoveredBin =
    hoveredBinIdx !== null && analytics ? analytics.histogram[hoveredBinIdx] ?? null : null;

  const itemCounts = useMemo(() => {
    const items = analytics?.items ?? [];
    return {
      all: items.length,
      poor_discrimination: items.filter((i) => i.quality_flag === "poor_discrimination").length,
      too_hard: items.filter((i) => i.difficulty_p < 0.25).length,
      too_easy: items.filter((i) => i.difficulty_p > 0.9).length,
    };
  }, [analytics?.items]);

  const filteredItems = useMemo(() => {
    const items = analytics?.items ?? [];
    if (itemFilter === "poor_discrimination") {
      return items.filter((i) => i.quality_flag === "poor_discrimination");
    }
    if (itemFilter === "too_hard") {
      return items.filter((i) => i.difficulty_p < 0.25);
    }
    if (itemFilter === "too_easy") {
      return items.filter((i) => i.difficulty_p > 0.9);
    }
    return items;
  }, [analytics?.items, itemFilter]);

  async function handleRunGrading() {
    if (!answerKey || sheets.length === 0) {
      setError("Scan at least one sheet and provide an answer key to grade.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await gradeSheets(sheets, answerKey, policy);
      onReportReady(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Grading failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleExport(fmt: "csv" | "xlsx") {
    if (!report) return;
    try {
      const blob = await exportReportFile(fmt, sheets, report);
      triggerBlobDownload(blob, fmt === "csv" ? "graded_results.csv" : "graded_report.xlsx");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed.");
    }
  }

  async function handleScorecard(grade: StudentGrade) {
    if (!report) return;
    try {
      const blob = await exportStudentScorecard(grade, report.exam_name);
      triggerBlobDownload(blob, `${grade.sheet_id}_scorecard.pdf`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scorecard export failed.");
    }
  }

  function renderSortIcon(key: SortKey) {
    if (sortKey !== key) return <ArrowUpDown className="w-3 h-3 opacity-40" />;
    return sortDir === "asc" ? (
      <ArrowUp className="w-3 h-3 text-[var(--ink-primary)]" />
    ) : (
      <ArrowDown className="w-3 h-3 text-[var(--ink-primary)]" />
    );
  }

  return (
    <div className="space-y-5">
      {/* Control Strip */}
      <section className="paper-card p-4 flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs space-y-1">
            <span className="section-label block">{t.scoringPolicy}</span>
            <select
              className="workbench-input"
              value={selectedPolicyName}
              onChange={(e) => setSelectedPolicyName(e.target.value)}
            >
              <option value="standard">Standard (+1 / 0)</option>
              <option value="yks_tyt">YKS / TYT (4 Wrong = -1 Correct)</option>
              <option value="kpss">KPSS (4 Wrong = -1 Correct)</option>
              <option value="lgs">LGS (3 Wrong = -1 Correct)</option>
              <option value="sat_legacy">Negative Quarter (+1 / -0.25)</option>
            </select>
          </label>

          <label className="text-xs space-y-1">
            <span className="section-label block">{t.uploadAnswerKey}</span>
            <input
              type="file"
              accept=".json"
              className="workbench-input text-xs"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                try {
                  const parsed = JSON.parse(await file.text()) as AnswerKey;
                  onUpdateAnswerKey(parsed);
                  const bks = Object.keys(parsed.booklets ?? {});
                  if (bks.length > 0) {
                    setSelectedBooklet(
                      parsed.default_booklet && bks.includes(parsed.default_booklet)
                        ? parsed.default_booklet
                        : bks[0]
                    );
                  }
                  setError(null);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Invalid answer key JSON");
                } finally {
                  e.target.value = "";
                }
              }}
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={loading || sheets.length === 0 || !answerKey}
            onClick={() => void handleRunGrading()}
            className="btn-accent"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            {loading ? t.grading : `${t.gradeSheetsBtn} (${sheets.length})`}
          </button>

          {report && (
            <>
              <button
                type="button"
                onClick={() => void handleExport("csv")}
                className="btn-secondary text-xs"
              >
                <Download className="w-3.5 h-3.5" /> CSV
              </button>
              <button
                type="button"
                onClick={() => void handleExport("xlsx")}
                className="btn-secondary text-xs"
              >
                <FileSpreadsheet className="w-3.5 h-3.5" /> {t.excelReport}
              </button>
            </>
          )}
        </div>
      </section>

      {error && (
        <div className="p-3 rounded-[5px] bg-[var(--signal-err-bg)] text-[var(--signal-err)] text-xs font-mono border border-red-200">
          {error}
        </div>
      )}

      {/* Answer Key Quick Editor */}
      {answerKey && answersEntries.length > 0 && (
        <section className="paper-card p-4 space-y-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <h2 className="section-label">
                {t.answerKeyHeader} · {answerKey.exam_name} ({answersEntries.length})
              </h2>
              {hasBooklets && (
                <select
                  aria-label="Select booklet"
                  className="workbench-input !py-0.5 !px-2 text-xs font-mono"
                  value={activeBooklet}
                  onChange={(e) => setSelectedBooklet(e.target.value)}
                >
                  {bookletNames.map((bk) => (
                    <option key={bk} value={bk}>
                      Booklet {bk}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <span className="text-[11px] font-mono text-[var(--ink-muted)]">
              {t.inlineEditHint}
            </span>
          </div>
          <div className="grid grid-cols-5 sm:grid-cols-10 gap-1.5 max-h-40 overflow-y-auto">
            {answersEntries.map(([qid, expected]) => {
              const display = Array.isArray(expected) ? expected.join("/") : expected;
              return (
                <div
                  key={qid}
                  className="flex items-center justify-between px-2 py-1 rounded-[4px] border border-[var(--border-hairline)] bg-[var(--surface-paper)] text-xs font-mono"
                >
                  <span className="text-[var(--ink-muted)]">{qid}</span>
                  <input
                    type="text"
                    maxLength={6}
                    className="w-9 text-right font-semibold bg-transparent focus:outline-none text-[var(--ink-primary)]"
                    value={display}
                    onChange={(e) => {
                      const rawVal = e.target.value.toUpperCase();
                      const parsedVal = rawVal.includes("/")
                        ? rawVal
                            .split("/")
                            .map((s) => s.trim())
                            .filter(Boolean)
                        : rawVal;
                      if (hasBooklets) {
                        const nextBooklet = {
                          ...(answerKey.booklets[activeBooklet] ?? {}),
                          [qid]: parsedVal,
                        };
                        onUpdateAnswerKey({
                          ...answerKey,
                          booklets: { ...answerKey.booklets, [activeBooklet]: nextBooklet },
                        });
                      } else {
                        const next = { ...answerKey.answers, [qid]: parsedVal };
                        onUpdateAnswerKey({ ...answerKey, answers: next });
                      }
                    }}
                  />
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Graded Analytics Results */}
      {report && analytics ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              { label: t.studentsGraded, val: String(analytics.student_count) },
              {
                label: t.meanScore,
                val: `${analytics.mean_score} (${analytics.mean_percentage}%)`,
              },
              {
                label: t.medianStd,
                val: `${analytics.median_score} / ${analytics.std_score}`,
              },
              {
                label: t.minMax,
                val: `${analytics.min_score} – ${analytics.max_score}`,
              },
              {
                label: t.kr20Reliability,
                val:
                  analytics.kr20_reliability !== null
                    ? analytics.kr20_reliability.toFixed(3)
                    : "N/A",
              },
            ].map((kpi) => (
              <div key={kpi.label} className="paper-card p-3.5">
                <p className="section-label">{kpi.label}</p>
                <p className="text-lg font-bold font-mono text-[var(--ink-primary)] mt-1 tabular-nums">
                  {kpi.val}
                </p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Score Histogram with Hover Telemetry */}
            <section className="lg:col-span-5 paper-card p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="section-label">{t.scoreDistribution}</h3>
                <span className="text-[11px] font-mono text-[var(--ink-primary)] tabular-nums">
                  {hoveredBin
                    ? `${hoveredBin.low}–${hoveredBin.high}%: ${hoveredBin.count} (${
                        totalStudents > 0
                          ? Math.round((hoveredBin.count / totalStudents) * 100)
                          : 0
                      }%)`
                    : `Med ${analytics.median_score}`}
                </span>
              </div>
              <div className="h-44 flex items-end gap-1.5 pt-4">
                {analytics.histogram.map((bin, idx) => {
                  const isHovered = hoveredBinIdx === idx;
                  return (
                    <div
                      key={bin.label}
                      onMouseEnter={() => setHoveredBinIdx(idx)}
                      onMouseLeave={() => setHoveredBinIdx(null)}
                      className="flex-1 flex flex-col items-center gap-1 h-full justify-end cursor-crosshair"
                    >
                      <span
                        className={`text-[10px] font-mono tabular-nums ${
                          isHovered
                            ? "text-[var(--accent-cobalt)] font-semibold"
                            : "text-[var(--ink-muted)]"
                        }`}
                      >
                        {bin.count > 0 ? bin.count : ""}
                      </span>
                      <div
                        className={`w-full rounded-t-[2px] transition-colors ${
                          isHovered
                            ? "bg-[var(--accent-cobalt)]"
                            : "bg-[var(--ink-primary)]"
                        }`}
                        style={{
                          height: `${Math.max(4, (bin.count / maxBin) * 100)}%`,
                          opacity: bin.count > 0 ? (isHovered ? 1 : 0.88) : 0.12,
                        }}
                      />
                      <span className="text-[9px] font-mono text-[var(--ink-muted)] tabular-nums">
                        {bin.low}
                      </span>
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Sortable Student Scoreboard */}
            <section className="lg:col-span-7 paper-card overflow-hidden">
              <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex items-center justify-between">
                <h3 className="section-label">{t.studentScoreboard}</h3>
                <span className="text-xs font-mono text-[var(--ink-muted)]">
                  {report.policy_name}
                </span>
              </div>
              <div className="overflow-x-auto max-h-60">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[var(--surface-subtle)] text-[var(--ink-secondary)] font-mono sticky top-0">
                    <tr>
                      <th className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => toggleSort("sheet_id")}
                          className="inline-flex items-center gap-1 hover:text-[var(--ink-primary)] cursor-pointer"
                        >
                          {t.colSheet} {renderSortIcon("sheet_id")}
                        </button>
                      </th>
                      <th className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => toggleSort("raw_score")}
                          className="inline-flex items-center gap-1 hover:text-[var(--ink-primary)] cursor-pointer"
                        >
                          {t.colScore} {renderSortIcon("raw_score")}
                        </button>
                      </th>
                      <th className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => toggleSort("percentage")}
                          className="inline-flex items-center gap-1 hover:text-[var(--ink-primary)] cursor-pointer"
                        >
                          % {renderSortIcon("percentage")}
                        </button>
                      </th>
                      <th className="px-3 py-2">+ / - / o</th>
                      <th className="px-3 py-2 text-right">PDF</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-hairline)] font-mono tabular-nums">
                    {sortedGrades.map((g) => (
                      <tr key={g.sheet_id} className="hover:bg-[var(--surface-paper)]">
                        <td className="px-3 py-2 font-medium">{g.sheet_id}</td>
                        <td className="px-3 py-2 font-semibold">
                          {g.raw_score} / {g.max_score}
                        </td>
                        <td className="px-3 py-2">{g.percentage.toFixed(1)}%</td>
                        <td className="px-3 py-2">
                          <span className="text-[var(--signal-ok)]">{g.correct}</span> /{" "}
                          <span className="text-[var(--signal-err)]">{g.incorrect}</span> /{" "}
                          <span className="text-[var(--ink-muted)]">{g.blank}</span>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <button
                            type="button"
                            onClick={() => void handleScorecard(g)}
                            className="inline-flex items-center gap-1 text-[var(--accent-cobalt)] hover:underline cursor-pointer"
                          >
                            <FileText className="w-3.5 h-3.5" /> PDF
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          {/* Item Psychometrics Table with Quality Filters & Inline Micro-Bars */}
          <section className="paper-card overflow-hidden">
            <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="section-label">{t.itemPsychometrics}</h3>
                <p className="text-[11px] text-[var(--ink-muted)] mt-0.5">
                  {t.itemPsychometricsSub}
                </p>
              </div>
              <div className="inline-flex items-center rounded-[5px] border border-[var(--border-strong)] overflow-hidden bg-[var(--surface-card)] text-xs font-mono">
                {(
                  [
                    { id: "all", label: t.filterAll, count: itemCounts.all },
                    {
                      id: "poor_discrimination",
                      label: t.filterFlagged,
                      count: itemCounts.poor_discrimination,
                    },
                    { id: "too_hard", label: t.filterHard, count: itemCounts.too_hard },
                    { id: "too_easy", label: t.filterEasy, count: itemCounts.too_easy },
                  ] as const
                ).map((f, idx) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setItemFilter(f.id)}
                    className={`px-2.5 py-1 inline-flex items-center gap-1 cursor-pointer transition-colors ${
                      idx > 0 ? "border-l border-[var(--border-hairline)]" : ""
                    } ${
                      itemFilter === f.id
                        ? "bg-[var(--ink-primary)] text-white"
                        : "text-[var(--ink-secondary)] hover:bg-[var(--surface-subtle)]"
                    }`}
                  >
                    <span>{f.label}</span>
                    <span className="opacity-70">{f.count}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto max-h-96">
              <table className="w-full text-xs text-left">
                <thead className="bg-[var(--surface-subtle)] text-[var(--ink-secondary)] font-mono sticky top-0 z-10">
                  <tr>
                    <th className="px-3 py-2">{t.colQuestion}</th>
                    <th className="px-3 py-2">{t.colKey}</th>
                    <th className="px-3 py-2">{t.colDifficulty}</th>
                    <th className="px-3 py-2">{t.colDiscrimination}</th>
                    <th className="px-3 py-2">{t.colOmit}</th>
                    <th className="px-3 py-2 min-w-[220px]">{t.colDistribution}</th>
                    <th className="px-3 py-2">{t.colQuality}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-hairline)] font-mono tabular-nums">
                  {filteredItems.map((item) => {
                    const expectedKeys = new Set(
                      item.expected
                        .split("/")
                        .map((k) => k.trim())
                        .filter(Boolean)
                    );
                    const distEntries = Object.entries(item.option_distribution);
                    const totalVotes = Math.max(
                      1,
                      distEntries.reduce((acc, [, c]) => acc + c, 0)
                    );

                    return (
                      <tr key={item.question_id} className="hover:bg-[var(--surface-paper)]">
                        <td className="px-3 py-2 font-semibold">{item.question_id}</td>
                        <td className="px-3 py-2 font-semibold text-[var(--signal-ok)]">
                          {item.expected}
                        </td>
                        <td className="px-3 py-2">{(item.difficulty_p * 100).toFixed(0)}%</td>
                        <td
                          className={`px-3 py-2 ${
                            item.discrimination_d < 0.2
                              ? "text-[var(--signal-err)] font-semibold"
                              : ""
                          }`}
                        >
                          {item.discrimination_d.toFixed(2)}
                        </td>
                        <td className="px-3 py-2">{(item.omit_rate * 100).toFixed(0)}%</td>
                        <td className="px-3 py-2">
                          <div className="space-y-1">
                            {/* Proportional Option Distribution Micro-Bar */}
                            <div className="h-2 w-full rounded-[2px] overflow-hidden flex bg-[var(--surface-well)]">
                              {distEntries.map(([opt, count]) => {
                                if (count <= 0) return null;
                                const pct = (count / totalVotes) * 100;
                                const isCorrect = expectedKeys.has(opt);
                                const isBlank = opt === "" || opt === "BLANK" || opt === "_";
                                const barColor = isCorrect
                                  ? "bg-[#0D7A52]"
                                  : isBlank
                                    ? "bg-[#B6B0A2]"
                                    : "bg-[#64748B]";
                                return (
                                  <div
                                    key={opt || "blank"}
                                    title={`${opt || "BLANK"}: ${count} (${Math.round(pct)}%)`}
                                    className={`${barColor} h-full border-r border-white/40 last:border-r-0`}
                                    style={{ width: `${pct}%` }}
                                  />
                                );
                              })}
                            </div>
                            <div className="flex flex-wrap gap-x-2 text-[10px] text-[var(--ink-secondary)]">
                              {distEntries.map(([opt, c]) => {
                                const isCorrect = expectedKeys.has(opt);
                                return (
                                  <span
                                    key={opt || "blank"}
                                    className={
                                      isCorrect ? "text-[var(--signal-ok)] font-semibold" : ""
                                    }
                                  >
                                    {opt || "–"}:{c}
                                  </span>
                                );
                              })}
                            </div>
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={`px-1.5 py-0.5 rounded-[3px] text-[10px] ${
                              item.quality_flag === "good"
                                ? "bg-[var(--signal-ok-bg)] text-[var(--signal-ok)]"
                                : item.quality_flag === "poor_discrimination"
                                  ? "bg-[var(--signal-err-bg)] text-[var(--signal-err)]"
                                  : "bg-[var(--signal-warn-bg)] text-[var(--signal-warn)]"
                            }`}
                          >
                            {item.quality_flag}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : (
        <div className="paper-card p-12 text-center space-y-2 text-[var(--ink-muted)]">
          <Award className="w-7 h-7 mx-auto opacity-45" />
          <p className="text-sm font-medium text-[var(--ink-secondary)]">{t.readyToGrade}</p>
          <p className="text-xs max-w-md mx-auto">{t.readyToGradeSub}</p>
        </div>
      )}
    </div>
  );
}
