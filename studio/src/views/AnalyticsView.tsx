import { useState } from "react";
import { Award, Download, FileSpreadsheet, FileText, Play } from "lucide-react";
import {
  exportReportFile,
  exportStudentScorecard,
  gradeSheets,
  triggerBlobDownload,
} from "../api/client";
import type {
  AnswerKey,
  GradingPolicy,
  GradingReport,
  SheetResult,
  StudentGrade,
} from "../types";

interface AnalyticsViewProps {
  sheets: SheetResult[];
  policies: GradingPolicy[];
  answerKey: AnswerKey | null;
  onUpdateAnswerKey: (key: AnswerKey) => void;
  report: GradingReport | null;
  onReportReady: (report: GradingReport) => void;
}

export function AnalyticsView({
  sheets,
  policies,
  answerKey,
  onUpdateAnswerKey,
  report,
  onReportReady,
}: AnalyticsViewProps) {
  const [selectedPolicyName, setSelectedPolicyName] = useState<string>("standard");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const answersEntries = answerKey ? Object.entries(answerKey.answers) : [];

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

  const analytics = report?.analytics;
  const maxBin = Math.max(1, ...(analytics?.histogram.map((b) => b.count) ?? [1]));

  return (
    <div className="space-y-5">
      {/* Control Strip */}
      <section className="paper-card p-4 flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs space-y-1">
            <span className="block font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
              Scoring Policy
            </span>
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
            <span className="block font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
              Upload Answer Key JSON
            </span>
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
                  setError(null);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "Invalid answer key JSON");
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
            <Play className="w-4 h-4" />
            {loading ? "Grading..." : `Grade ${sheets.length} Sheet${sheets.length === 1 ? "" : "s"}`}
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
                <FileSpreadsheet className="w-3.5 h-3.5" /> Excel Report
              </button>
            </>
          )}
        </div>
      </section>

      {error && (
        <div className="p-3 rounded-lg bg-[var(--signal-err-bg)] text-[var(--signal-err)] text-xs border border-red-200">
          {error}
        </div>
      )}

      {/* Answer Key Quick Editor */}
      {answerKey && answersEntries.length > 0 && (
        <section className="paper-card p-4 space-y-2.5">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
              Answer Key — {answerKey.exam_name} ({answersEntries.length} questions)
            </h2>
            <span className="text-xs text-[var(--ink-muted)]">Click any key to edit inline</span>
          </div>
          <div className="grid grid-cols-5 sm:grid-cols-10 gap-1.5 max-h-40 overflow-y-auto">
            {answersEntries.map(([qid, expected]) => {
              const display = Array.isArray(expected) ? expected.join("/") : expected;
              return (
                <div
                  key={qid}
                  className="flex items-center justify-between px-2 py-1 rounded border border-[var(--border-hairline)] bg-[var(--surface-paper)] text-xs font-mono"
                >
                  <span className="text-[var(--ink-muted)]">{qid}</span>
                  <input
                    type="text"
                    maxLength={4}
                    className="w-8 text-right font-semibold bg-transparent focus:outline-none text-[var(--ink-primary)]"
                    value={display}
                    onChange={(e) => {
                      const next = { ...answerKey.answers, [qid]: e.target.value.toUpperCase() };
                      onUpdateAnswerKey({ ...answerKey, answers: next });
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
              { label: "Students Graded", val: String(analytics.student_count) },
              { label: "Mean Score", val: `${analytics.mean_score} (${analytics.mean_percentage}%)` },
              { label: "Median / Std", val: `${analytics.median_score} / ${analytics.std_score}` },
              { label: "Min – Max", val: `${analytics.min_score} – ${analytics.max_score}` },
              {
                label: "KR-20 Reliability",
                val: analytics.kr20_reliability !== null ? analytics.kr20_reliability.toFixed(3) : "N/A",
              },
            ].map((kpi) => (
              <div key={kpi.label} className="paper-card p-3.5">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-muted)]">
                  {kpi.label}
                </p>
                <p className="text-lg font-bold font-mono text-[var(--ink-primary)] mt-1">
                  {kpi.val}
                </p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Score Histogram */}
            <section className="lg:col-span-5 paper-card p-4 space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
                Score Distribution (%)
              </h3>
              <div className="h-44 flex items-end gap-1.5 pt-4">
                {analytics.histogram.map((bin) => (
                  <div key={bin.label} className="flex-1 flex flex-col items-center gap-1 h-full justify-end">
                    <span className="text-[10px] font-mono text-[var(--ink-muted)]">
                      {bin.count > 0 ? bin.count : ""}
                    </span>
                    <div
                      className="w-full rounded-t bg-[var(--ink-primary)] transition-all"
                      style={{ height: `${Math.max(4, (bin.count / maxBin) * 100)}%`, opacity: bin.count > 0 ? 0.9 : 0.12 }}
                    />
                    <span className="text-[9px] font-mono text-[var(--ink-muted)]">
                      {bin.low}
                    </span>
                  </div>
                ))}
              </div>
            </section>

            {/* Student Scoreboard */}
            <section className="lg:col-span-7 paper-card overflow-hidden">
              <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
                  Student Scoreboard
                </h3>
                <span className="text-xs font-mono text-[var(--ink-muted)]">
                  Policy: {report.policy_name}
                </span>
              </div>
              <div className="overflow-x-auto max-h-60">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[var(--surface-subtle)] text-[var(--ink-secondary)] font-mono">
                    <tr>
                      <th className="px-3 py-2">Sheet</th>
                      <th className="px-3 py-2">Score</th>
                      <th className="px-3 py-2">%</th>
                      <th className="px-3 py-2">+ / - / o</th>
                      <th className="px-3 py-2 text-right">PDF</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-hairline)] font-mono">
                    {report.grades.map((g) => (
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
                            <FileText className="w-3.5 h-3.5" /> Card
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          {/* Item Psychometrics Table */}
          <section className="paper-card overflow-hidden">
            <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
                Classical Test Theory — Item Psychometrics
              </h3>
              <span className="text-xs text-[var(--ink-muted)]">
                Difficulty (p) · Upper/Lower 27% Discrimination (D) · Distractor Frequencies
              </span>
            </div>
            <div className="overflow-x-auto max-h-80">
              <table className="w-full text-xs text-left">
                <thead className="bg-[var(--surface-subtle)] text-[var(--ink-secondary)] font-mono sticky top-0">
                  <tr>
                    <th className="px-3 py-2">Question</th>
                    <th className="px-3 py-2">Key</th>
                    <th className="px-3 py-2">Difficulty (p)</th>
                    <th className="px-3 py-2">Discrimination (D)</th>
                    <th className="px-3 py-2">Omit %</th>
                    <th className="px-3 py-2">Distribution</th>
                    <th className="px-3 py-2">Quality</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-hairline)] font-mono">
                  {analytics.items.map((item) => (
                    <tr key={item.question_id} className="hover:bg-[var(--surface-paper)]">
                      <td className="px-3 py-2 font-semibold">{item.question_id}</td>
                      <td className="px-3 py-2">{item.expected}</td>
                      <td className="px-3 py-2">{(item.difficulty_p * 100).toFixed(0)}%</td>
                      <td className="px-3 py-2">{item.discrimination_d.toFixed(2)}</td>
                      <td className="px-3 py-2">{(item.omit_rate * 100).toFixed(0)}%</td>
                      <td className="px-3 py-2 text-[11px] text-[var(--ink-secondary)]">
                        {Object.entries(item.option_distribution)
                          .map(([opt, c]) => `${opt}:${c}`)
                          .join("  ")}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] ${
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
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : (
        <div className="paper-card p-12 text-center space-y-2 text-[var(--ink-muted)]">
          <Award className="w-8 h-8 mx-auto opacity-50" />
          <p className="text-sm font-medium text-[var(--ink-secondary)]">Ready to grade</p>
          <p className="text-xs max-w-md mx-auto">
            Scan sheets in the Scan & Review workspace, select your scoring policy (including 4-wrong-1-right YKS/KPSS or LGS presets), and run grading for instant item psychometrics and printable PDF scorecards.
          </p>
        </div>
      )}
    </div>
  );
}
