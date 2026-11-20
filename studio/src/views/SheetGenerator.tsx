import { useEffect, useState } from "react";
import { Download, FileText, Package, Play, RefreshCw } from "lucide-react";
import {
  downloadGeneratedBundle,
  generateSheet,
  triggerBlobDownload,
} from "../api/client";
import type { AnswerKey, GenerateResponse, PresetBundle, SheetSpec, Template } from "../types";

interface SheetGeneratorProps {
  presets: PresetBundle[];
  onActivateGenerated: (template: Template, answerKey: AnswerKey) => void;
}

export function SheetGenerator({ presets, onActivateGenerated }: SheetGeneratorProps) {
  const [spec, setSpec] = useState<SheetSpec | null>(presets[1]?.spec ?? presets[0]?.spec ?? null);
  const [generated, setGenerated] = useState<GenerateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!spec && presets.length > 0) {
      const initial = presets.find((p) => p.id === "standard_mcq_40")?.spec ?? presets[0].spec;
      setSpec(initial);
    }
  }, [presets, spec]);

  useEffect(() => {
    if (!spec) return;
    const controller = new AbortController();
    let active = true;
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      generateSheet(spec, controller.signal)
        .then((res) => {
          if (active) setGenerated(res);
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === "AbortError") return;
          if (active) setError(err instanceof Error ? err.message : "Generation failed.");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 300);
    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [spec]);

  async function handleDownloadZip() {
    if (!spec) return;
    try {
      const blob = await downloadGeneratedBundle(spec);
      triggerBlobDownload(blob, `${spec.preset_id}_bundle.zip`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed.");
    }
  }

  function handleDownloadPdf() {
    if (!generated) return;
    const raw = atob(generated.pdf_base64);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
    triggerBlobDownload(new Blob([bytes], { type: "application/pdf" }), generated.filename);
  }

  if (!spec) {
    return <div className="paper-card p-8 text-center text-sm text-[var(--ink-muted)]">Loading presets...</div>;
  }

  const maxColsForOptions = spec.options.length >= 5 ? 4 : 5;
  const minRowsPerCol = Math.max(5, Math.ceil(spec.num_questions / maxColsForOptions));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
      {/* Configuration Column */}
      <aside className="lg:col-span-5 space-y-4">
        <section className="paper-card p-4 space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
            Built-in Exam Presets
          </h2>
          <div className="grid grid-cols-2 gap-2">
            {presets.map((p) => {
              const isSelected = spec.preset_id === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setSpec(structuredClone(p.spec))}
                  className={`p-3 rounded-lg border text-left transition-colors cursor-pointer ${
                    isSelected
                      ? "border-[var(--ink-primary)] bg-[var(--surface-subtle)]"
                      : "border-[var(--border-hairline)] bg-white hover:bg-[var(--surface-subtle)]"
                  }`}
                >
                  <div className="text-xs font-semibold text-[var(--ink-primary)] truncate">
                    {p.id}
                  </div>
                  <div className="text-[11px] font-mono text-[var(--ink-muted)] mt-0.5">
                    {p.spec.num_questions}Q · {p.spec.options.join("")} · {p.spec.page_format}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="paper-card p-4 space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
            Customize Optical Form
          </h2>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <label className="col-span-2 space-y-1">
              <span className="text-[var(--ink-secondary)]">Sheet Title</span>
              <input
                type="text"
                className="workbench-input w-full"
                value={spec.title}
                onChange={(e) => setSpec({ ...spec, title: e.target.value })}
              />
            </label>

            <label className="col-span-2 space-y-1">
              <span className="text-[var(--ink-secondary)]">Subtitle / Instructions</span>
              <input
                type="text"
                className="workbench-input w-full"
                value={spec.subtitle}
                onChange={(e) => setSpec({ ...spec, subtitle: e.target.value })}
              />
            </label>

            <label className="space-y-1">
              <span className="text-[var(--ink-secondary)]">Questions (5–120)</span>
              <input
                type="number"
                min={5}
                max={120}
                className="workbench-input w-full font-mono"
                value={spec.num_questions}
                onChange={(e) => {
                  const nextQ = Math.max(5, Math.min(120, Number(e.target.value) || 20));
                  const requiredRows = Math.max(5, Math.ceil(nextQ / maxColsForOptions));
                  setSpec({
                    ...spec,
                    num_questions: nextQ,
                    questions_per_column: Math.min(30, Math.max(spec.questions_per_column, requiredRows)),
                  });
                }}
              />
            </label>

            <label className="space-y-1">
              <span className="text-[var(--ink-secondary)]">
                Rows / Column ({minRowsPerCol}–30)
              </span>
              <input
                type="number"
                min={minRowsPerCol}
                max={30}
                className="workbench-input w-full font-mono"
                value={spec.questions_per_column}
                onChange={(e) =>
                  setSpec({
                    ...spec,
                    questions_per_column: Math.max(
                      minRowsPerCol,
                      Math.min(30, Number(e.target.value) || minRowsPerCol)
                    ),
                  })
                }
              />
            </label>

            <label className="space-y-1">
              <span className="text-[var(--ink-secondary)]">Page Format</span>
              <select
                className="workbench-input w-full"
                value={spec.page_format}
                onChange={(e) =>
                  setSpec({ ...spec, page_format: e.target.value as "A4" | "LETTER" })
                }
              >
                <option value="A4">A4 (210 × 297 mm)</option>
                <option value="LETTER">US Letter (8.5 × 11 in)</option>
              </select>
            </label>

            <label className="space-y-1">
              <span className="text-[var(--ink-secondary)]">Options</span>
              <select
                className="workbench-input w-full font-mono"
                value={spec.options.join("")}
                onChange={(e) => {
                  const nextOpts = e.target.value.split("");
                  const nextMaxCols = nextOpts.length >= 5 ? 4 : 5;
                  const reqRows = Math.max(5, Math.ceil(spec.num_questions / nextMaxCols));
                  setSpec({
                    ...spec,
                    options: nextOpts,
                    questions_per_column: Math.min(30, Math.max(spec.questions_per_column, reqRows)),
                  });
                }}
              >
                <option value="ABCD">A – D (4 choices)</option>
                <option value="ABCDE">A – E (5 choices)</option>
              </select>
            </label>

            <label className="col-span-2 flex items-center gap-2 pt-1 cursor-pointer">
              <input
                type="checkbox"
                checked={spec.include_booklet}
                onChange={(e) => setSpec({ ...spec, include_booklet: e.target.checked })}
              />
              <span className="text-[var(--ink-primary)]">Include Booklet Selector (A / B / C / D)</span>
            </label>
          </div>

          {error && (
            <div className="text-xs p-2.5 rounded bg-[var(--signal-err-bg)] text-[var(--signal-err)]">
              {error}
            </div>
          )}

          <div className="pt-2 border-t border-[var(--border-hairline)] flex flex-col gap-2">
            <button
              type="button"
              onClick={() => void handleDownloadZip()}
              className="btn-accent w-full justify-center"
            >
              <Package className="w-4 h-4" /> Download Bundle (PDF + template.json + Key)
            </button>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={handleDownloadPdf}
                disabled={!generated}
                className="btn-secondary justify-center text-xs"
              >
                <FileText className="w-3.5 h-3.5" /> Printable PDF
              </button>
              <button
                type="button"
                disabled={!generated}
                onClick={() => {
                  if (!generated) return;
                  triggerBlobDownload(
                    new Blob([JSON.stringify(generated.template, null, 2)], {
                      type: "application/json",
                    }),
                    `${spec.preset_id}_template.json`
                  );
                }}
                className="btn-secondary justify-center text-xs"
              >
                <Download className="w-3.5 h-3.5" /> template.json
              </button>
            </div>
            <button
              type="button"
              disabled={!generated}
              onClick={() => {
                if (generated) {
                  onActivateGenerated(generated.template, generated.sample_answer_key);
                }
              }}
              className="btn-primary w-full justify-center text-xs"
            >
              <Play className="w-3.5 h-3.5" /> Activate Template in Scanner & Grader
            </button>
          </div>
        </section>
      </aside>

      {/* Live Print Preview */}
      <section className="lg:col-span-7 paper-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold">Live ArUco Sheet Print Preview</h2>
            <p className="text-xs text-[var(--ink-muted)] font-mono">
              Zero-calibration guarantee: ArUco corners [0,1,2,3] map directly to exact template coordinates.
            </p>
          </div>
          {loading && <RefreshCw className="w-4 h-4 animate-spin text-[var(--ink-muted)]" />}
        </div>

        <div className="bg-[var(--surface-subtle)] p-5 flex justify-center min-h-[600px]">
          {generated ? (
            <img
              src={generated.preview_data_url}
              alt="Generated printable optical answer sheet"
              className="max-h-[72vh] w-auto rounded border border-[var(--border-strong)] shadow-sm bg-white"
            />
          ) : (
            <div className="my-auto text-xs text-[var(--ink-muted)]">Generating vector PDF preview...</div>
          )}
        </div>
      </section>
    </div>
  );
}
