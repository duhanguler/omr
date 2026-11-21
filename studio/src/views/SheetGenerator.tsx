import { useEffect, useState } from "react";
import { Download, FileText, Package, Play, Printer, RefreshCw } from "lucide-react";
import {
  downloadGeneratedBundle,
  generateSheet,
  triggerBlobDownload,
} from "../api/client";
import type { Dictionary } from "../i18n";
import type { AnswerKey, GenerateResponse, PresetBundle, SheetSpec, Template } from "../types";

interface SheetGeneratorProps {
  t: Dictionary;
  presets: PresetBundle[];
  onActivateGenerated: (template: Template, answerKey: AnswerKey) => void;
}

function pdfBase64ToBlob(b64: string): Blob {
  const raw = atob(b64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return new Blob([bytes], { type: "application/pdf" });
}

export function SheetGenerator({ t, presets, onActivateGenerated }: SheetGeneratorProps) {
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
    triggerBlobDownload(pdfBase64ToBlob(generated.pdf_base64), generated.filename);
  }

  function handlePrintPdf() {
    if (!generated) return;
    const blob = pdfBase64ToBlob(generated.pdf_base64);
    const url = URL.createObjectURL(blob);
    const popup = window.open(url, "_blank", "noopener,noreferrer");
    if (!popup) {
      // Fallback when browser blocks popups: trigger direct download
      triggerBlobDownload(blob, generated.filename);
    }
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  if (!spec) {
    return (
      <div className="paper-card p-8 text-center text-xs font-mono text-[var(--ink-muted)]">
        {t.loading}
      </div>
    );
  }

  const maxColsForOptions = spec.options.length >= 5 ? 4 : 5;
  const minRowsPerCol = Math.max(5, Math.ceil(spec.num_questions / maxColsForOptions));
  const paperDimensions = spec.page_format === "A4" ? "A4 · 210×297 mm" : "LETTER · 8.5×11 in";
  const columnCount = Math.ceil(spec.num_questions / spec.questions_per_column);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
      {/* Configuration Column */}
      <aside className="lg:col-span-5 space-y-4">
        <section className="paper-card p-4 space-y-3">
          <h2 className="section-label">{t.builtinPresets}</h2>
          <div className="grid grid-cols-2 gap-2">
            {presets.map((p) => {
              const isSelected = spec.preset_id === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setSpec(structuredClone(p.spec))}
                  className={`p-2.5 rounded-[5px] border text-left transition-colors cursor-pointer ${
                    isSelected
                      ? "border-[var(--ink-primary)] bg-[var(--surface-subtle)]"
                      : "border-[var(--border-hairline)] bg-white hover:bg-[var(--surface-subtle)]"
                  }`}
                >
                  <div className="text-xs font-semibold font-mono text-[var(--ink-primary)] truncate">
                    {p.id}
                  </div>
                  <div className="text-[11px] font-mono text-[var(--ink-muted)] mt-0.5 tabular-nums">
                    {p.spec.num_questions}Q · {p.spec.options.join("")} · {p.spec.page_format}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="paper-card p-4 space-y-3">
          <h2 className="section-label">{t.customizeForm}</h2>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <label className="col-span-2 space-y-1">
              <span className="text-[var(--ink-secondary)]">{t.sheetTitle}</span>
              <input
                type="text"
                className="workbench-input w-full"
                value={spec.title}
                onChange={(e) => setSpec({ ...spec, title: e.target.value })}
              />
            </label>

            <label className="col-span-2 space-y-1">
              <span className="text-[var(--ink-secondary)]">{t.subtitleLabel}</span>
              <input
                type="text"
                className="workbench-input w-full"
                value={spec.subtitle}
                onChange={(e) => setSpec({ ...spec, subtitle: e.target.value })}
              />
            </label>

            <label className="space-y-1">
              <span className="text-[var(--ink-secondary)]">{t.questionsLabel}</span>
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
                    questions_per_column: Math.min(
                      30,
                      Math.max(spec.questions_per_column, requiredRows)
                    ),
                  });
                }}
              />
            </label>

            <label className="space-y-1">
              <span className="text-[var(--ink-secondary)]">
                {t.rowsPerColLabel} ({minRowsPerCol}–30)
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
              <span className="text-[var(--ink-secondary)]">{t.pageFormat}</span>
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
              <span className="text-[var(--ink-secondary)]">{t.optionsSelect}</span>
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
                <option value="ABCD">A – D (4)</option>
                <option value="ABCDE">A – E (5)</option>
              </select>
            </label>

            <label className="col-span-2 flex items-center gap-2 pt-1 cursor-pointer">
              <input
                type="checkbox"
                checked={spec.include_booklet}
                onChange={(e) => setSpec({ ...spec, include_booklet: e.target.checked })}
              />
              <span className="text-[var(--ink-primary)]">{t.includeBooklet}</span>
            </label>
          </div>

          {error && (
            <div className="text-xs font-mono p-2.5 rounded-[5px] bg-[var(--signal-err-bg)] text-[var(--signal-err)] border border-red-200">
              {error}
            </div>
          )}

          <div className="pt-2.5 border-t border-[var(--border-hairline)] flex flex-col gap-2">
            <button
              type="button"
              onClick={() => void handleDownloadZip()}
              className="btn-accent w-full justify-center"
            >
              <Package className="w-4 h-4" /> {t.downloadBundle}
            </button>
            <div className="grid grid-cols-3 gap-1.5">
              <button
                type="button"
                onClick={handleDownloadPdf}
                disabled={!generated}
                className="btn-secondary justify-center text-xs !px-2"
              >
                <FileText className="w-3.5 h-3.5" /> {t.printablePdf}
              </button>
              <button
                type="button"
                onClick={handlePrintPdf}
                disabled={!generated}
                className="btn-secondary justify-center text-xs !px-2"
              >
                <Printer className="w-3.5 h-3.5" /> {t.printSheet}
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
                className="btn-secondary justify-center text-xs !px-2"
              >
                <Download className="w-3.5 h-3.5" /> JSON
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
              <Play className="w-3.5 h-3.5" /> {t.activateTemplate}
            </button>
          </div>
        </section>
      </aside>

      {/* Live Print Preview */}
      <section className="lg:col-span-7 paper-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-[var(--ink-primary)]">
              {t.livePrintPreview}
            </h2>
            <p className="text-xs text-[var(--ink-muted)]">{t.livePrintSub}</p>
          </div>
          {loading && <RefreshCw className="w-4 h-4 animate-spin text-[var(--ink-muted)] shrink-0" />}
        </div>

        {/* Print Specification Telemetry Bar */}
        <div className="px-4 py-1.5 border-b border-[var(--border-hairline)] bg-[var(--surface-paper)] flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-mono text-[var(--ink-secondary)]">
          <span>{paperDimensions}</span>
          <span className="text-[var(--border-strong)]">·</span>
          <span>200 DPI</span>
          <span className="text-[var(--border-strong)]">·</span>
          <span>
            {spec.num_questions}Q ({columnCount} col × {spec.options.join("")})
          </span>
          <span className="text-[var(--border-strong)]">·</span>
          <span>ArUco [0,1,2,3]</span>
          <span className="text-[var(--border-strong)]">·</span>
          <span className="text-[var(--signal-ok)]">QR Auto-ID</span>
        </div>

        <div className="optical-stage p-5 flex justify-center min-h-[600px]">
          {generated ? (
            <img
              src={generated.preview_data_url}
              alt="Generated printable optical answer sheet"
              className="max-h-[72vh] w-auto border border-[var(--border-strong)] bg-white"
            />
          ) : (
            <div className="my-auto text-xs font-mono text-[var(--ink-muted)]">
              {t.generatingPreview}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
