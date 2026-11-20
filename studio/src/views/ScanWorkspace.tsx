import { useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileUp,
  ScanLine,
  Upload,
  XCircle,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { exportReportFile, scanFiles, triggerBlobDownload } from "../api/client";
import type { PresetBundle, ScanResponse, SheetResult, Template } from "../types";

interface ScanWorkspaceProps {
  presets: PresetBundle[];
  activeTemplate: Template | null;
  onSelectTemplate: (template: Template) => void;
  scanResponse: ScanResponse | null;
  onScanComplete: (response: ScanResponse) => void;
  onApplyOverride: (sheetId: string, fieldId: string, value: string) => void;
  onProceedToGrading: () => void;
}

export function ScanWorkspace({
  presets,
  activeTemplate,
  onSelectTemplate,
  scanResponse,
  onScanComplete,
  onApplyOverride,
  onProceedToGrading,
}: ScanWorkspaceProps) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [activeSheetId, setActiveSheetId] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<"review" | "all">("review");
  const [zoom, setZoom] = useState<number>(100);
  const [searchTerm, setSearchTerm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manualEdits, setManualEdits] = useState<Record<string, string>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);
  const templateInputRef = useRef<HTMLInputElement>(null);

  const sheets = scanResponse?.sheets ?? [];
  const currentSheet: SheetResult | null =
    sheets.find((s) => s.sheet_id === activeSheetId) ?? sheets[0] ?? null;
  const currentOverlay = currentSheet ? scanResponse?.overlays[currentSheet.sheet_id] : undefined;

  async function handleRunScan() {
    if (!activeTemplate) {
      setError("Please select or upload a template first.");
      return;
    }
    if (selectedFiles.length === 0) {
      setError("Please drop or choose at least one image or PDF file.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await scanFiles(selectedFiles, activeTemplate);
      onScanComplete(response);
      if (response.sheets.length > 0) {
        setActiveSheetId(response.sheets[0].sheet_id);
        setInspectorTab(response.sheets[0].review_items.length > 0 ? "review" : "all");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleTemplateUpload(file: File) {
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as Template;
      onSelectTemplate(parsed);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? `Invalid template JSON: ${err.message}` : "Invalid JSON");
    }
  }

  async function handleExport(fmt: "csv" | "xlsx") {
    if (!scanResponse) return;
    try {
      const blob = await exportReportFile(fmt, scanResponse.sheets, null);
      triggerBlobDownload(blob, fmt === "csv" ? "omrkit_results.csv" : "omrkit_report.xlsx");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed.");
    }
  }

  const totalFlags = sheets.reduce((acc, s) => acc + s.review_items.length, 0);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
      {/* Left Control Rail */}
      <aside className="lg:col-span-3 space-y-4">
        <section className="paper-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
              1. Active Template
            </h2>
            <button
              type="button"
              onClick={() => templateInputRef.current?.click()}
              className="text-xs font-medium text-[var(--accent-cobalt)] hover:underline cursor-pointer"
            >
              Upload JSON
            </button>
            <input
              ref={templateInputRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleTemplateUpload(file);
              }}
            />
          </div>

          <select
            id="scan-template-select"
            className="workbench-input w-full"
            value={presets.some((p) => p.template.name === activeTemplate?.name) ? activeTemplate?.name ?? "" : "__custom__"}
            onChange={(e) => {
              const found = presets.find((p) => p.template.name === e.target.value);
              if (found) onSelectTemplate(found.template);
            }}
          >
            {presets.map((p) => (
              <option key={p.id} value={p.template.name}>
                {p.spec.title} ({p.spec.num_questions}Q)
              </option>
            ))}
            {activeTemplate && !presets.some((p) => p.template.name === activeTemplate.name) && (
              <option value="__custom__">Custom: {activeTemplate.name}</option>
            )}
          </select>

          {activeTemplate && (
            <div className="text-xs text-[var(--ink-secondary)] font-mono flex flex-wrap gap-x-3 gap-y-1 pt-1">
              <span>{activeTemplate.page_width}×{activeTemplate.page_height}px</span>
              <span>mode:{activeTemplate.registration.mode}</span>
              <span>{activeTemplate.blocks.length} blocks</span>
            </div>
          )}
        </section>

        <section className="paper-card p-4 space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
            2. Optical Sheets (JPG / PNG / PDF)
          </h2>

          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const dropped = Array.from(e.dataTransfer.files);
              if (dropped.length) setSelectedFiles(dropped);
            }}
            onClick={() => fileInputRef.current?.click()}
            className="border border-dashed border-[var(--border-strong)] rounded-lg p-5 text-center cursor-pointer hover:bg-[var(--surface-subtle)] transition-colors"
          >
            <Upload className="w-5 h-5 mx-auto mb-2 text-[var(--ink-secondary)]" />
            <p className="text-sm font-medium text-[var(--ink-primary)]">
              Drop scanned sheets or multi-page PDF
            </p>
            <p className="text-xs text-[var(--ink-muted)] mt-1">
              Auto-rotates EXIF & ArUco 0°/90°/180°/270°
            </p>
            <input
              ref={fileInputRef}
              id="scan-files-input"
              type="file"
              multiple
              accept="image/*,.pdf"
              className="hidden"
              onChange={(e) => {
                if (e.target.files) setSelectedFiles(Array.from(e.target.files));
              }}
            />
          </div>

          {selectedFiles.length > 0 && (
            <ul className="text-xs space-y-1 max-h-32 overflow-y-auto">
              {selectedFiles.map((f) => (
                <li
                  key={`${f.name}-${f.size}`}
                  className="flex items-center justify-between px-2 py-1 rounded bg-[var(--surface-subtle)] font-mono"
                >
                  <span className="truncate">{f.name}</span>
                  <span className="text-[var(--ink-muted)] ml-2 shrink-0">
                    {(f.size / 1024).toFixed(0)} KB
                  </span>
                </li>
              ))}
            </ul>
          )}

          {error && (
            <div className="text-xs p-2.5 rounded-md bg-[var(--signal-err-bg)] text-[var(--signal-err)] border border-red-200">
              {error}
            </div>
          )}

          <button
            id="run-scan-btn"
            type="button"
            disabled={loading || selectedFiles.length === 0}
            onClick={() => void handleRunScan()}
            className="btn-accent w-full justify-center"
          >
            <ScanLine className="w-4 h-4" />
            {loading ? "Scanning..." : `Scan ${selectedFiles.length || ""} Sheet${selectedFiles.length === 1 ? "" : "s"}`}
          </button>
        </section>

        {sheets.length > 0 && (
          <section className="paper-card p-4 space-y-2.5">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--ink-secondary)]">
                Scanned Batch ({sheets.length})
              </h2>
              <span className="text-xs font-mono text-[var(--ink-muted)]">
                {scanResponse?.total_elapsed_ms.toFixed(0)} ms
              </span>
            </div>
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {sheets.map((s) => {
                const active = s.sheet_id === currentSheet?.sheet_id;
                return (
                  <button
                    key={s.sheet_id}
                    type="button"
                    onClick={() => setActiveSheetId(s.sheet_id)}
                    className={`w-full text-left px-2.5 py-2 rounded-md border text-xs transition-colors cursor-pointer ${
                      active
                        ? "border-[var(--ink-primary)] bg-[var(--surface-subtle)]"
                        : "border-transparent hover:bg-[var(--surface-subtle)]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-medium truncate">{s.sheet_id}</span>
                      {s.error ? (
                        <XCircle className="w-3.5 h-3.5 text-[var(--signal-err)] shrink-0" />
                      ) : s.review_items.length > 0 ? (
                        <span className="px-1.5 py-0.5 rounded bg-[var(--signal-warn-bg)] text-[var(--signal-warn)] font-mono text-[10px]">
                          {s.review_items.length} review
                        </span>
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5 text-[var(--signal-ok)] shrink-0" />
                      )}
                    </div>
                    <div className="text-[11px] text-[var(--ink-muted)] mt-0.5 font-mono">
                      {s.error
                        ? "Registration error"
                        : `${(s.overall_confidence * 100).toFixed(1)}% conf · ${s.elapsed_ms.toFixed(0)}ms`}
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="pt-2 border-t border-[var(--border-hairline)] flex flex-col gap-2">
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => void handleExport("csv")}
                  className="btn-secondary justify-center text-xs"
                >
                  <Download className="w-3.5 h-3.5" /> CSV
                </button>
                <button
                  type="button"
                  onClick={() => void handleExport("xlsx")}
                  className="btn-secondary justify-center text-xs"
                >
                  <FileSpreadsheet className="w-3.5 h-3.5" /> Excel
                </button>
              </div>
              <button
                type="button"
                onClick={onProceedToGrading}
                className="btn-primary w-full justify-center text-xs"
              >
                Grade & Analyze ({sheets.length}) <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </section>
        )}
      </aside>

      {/* Center Annotated Sheet Viewer */}
      <section className="lg:col-span-5 paper-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[var(--border-hairline)] flex items-center justify-between gap-2 bg-[var(--surface-card)]">
          <div>
            <h2 className="text-sm font-semibold text-[var(--ink-primary)]">
              {currentSheet ? currentSheet.source_file : "Optical Verification Canvas"}
            </h2>
            <p className="text-xs text-[var(--ink-muted)] font-mono">
              {currentSheet
                ? `Reg: ${currentSheet.registration_method} (${(currentSheet.registration_score * 100).toFixed(0)}%) · Rot: ${currentSheet.rotation_applied}°`
                : "Upload sheets on the left to inspect bubble detections"}
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setZoom((z) => Math.max(50, z - 25))}
              className="btn-secondary !px-2 !py-1.5"
              title="Zoom out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-xs font-mono w-11 text-center">{zoom}%</span>
            <button
              type="button"
              onClick={() => setZoom((z) => Math.min(200, z + 25))}
              className="btn-secondary !px-2 !py-1.5"
              title="Zoom in"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="bg-[var(--surface-subtle)] min-h-[540px] max-h-[74vh] overflow-auto flex items-start justify-center p-4">
          {currentSheet?.error ? (
            <div className="my-auto max-w-md text-center space-y-2 p-6 paper-card">
              <XCircle className="w-8 h-8 text-[var(--signal-err)] mx-auto" />
              <p className="text-sm font-semibold">Sheet Alignment Failed</p>
              <p className="text-xs text-[var(--ink-secondary)] font-mono">{currentSheet.error}</p>
            </div>
          ) : currentOverlay ? (
            <img
              src={currentOverlay}
              alt={`Annotated scan of ${currentSheet?.source_file}`}
              style={{ width: `${zoom}%` }}
              className="max-w-none rounded shadow-sm border border-[var(--border-hairline)] bg-white"
            />
          ) : (
            <div className="my-auto text-center max-w-sm space-y-2 text-[var(--ink-muted)]">
              <FileUp className="w-8 h-8 mx-auto opacity-50" />
              <p className="text-sm font-medium text-[var(--ink-secondary)]">
                No sheet scanned yet
              </p>
              <p className="text-xs leading-relaxed">
                Select a preset or custom template, drop scanned JPG/PNG photos or a multi-page
                PDF, and inspect green/amber/red bubble confidence overlays here.
              </p>
            </div>
          )}
        </div>
      </section>

      {/* Right HITL Review & Responses Inspector */}
      <section className="lg:col-span-4 paper-card overflow-hidden">
        <div className="border-b border-[var(--border-hairline)] flex">
          <button
            type="button"
            onClick={() => setInspectorTab("review")}
            className={`flex-1 py-3 px-3 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
              inspectorTab === "review"
                ? "border-[var(--ink-primary)] text-[var(--ink-primary)]"
                : "border-transparent text-[var(--ink-muted)] hover:text-[var(--ink-primary)]"
            }`}
          >
            HITL Review Queue ({currentSheet?.review_items.length ?? totalFlags})
          </button>
          <button
            type="button"
            onClick={() => setInspectorTab("all")}
            className={`flex-1 py-3 px-3 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
              inspectorTab === "all"
                ? "border-[var(--ink-primary)] text-[var(--ink-primary)]"
                : "border-transparent text-[var(--ink-muted)] hover:text-[var(--ink-primary)]"
            }`}
          >
            All Readings ({currentSheet ? Object.keys(currentSheet.fields).length : 0})
          </button>
        </div>

        <div className="p-4 max-h-[70vh] overflow-y-auto space-y-3">
          {!currentSheet ? (
            <p className="text-xs text-[var(--ink-muted)] py-8 text-center">
              Scan results and low-confidence review items will appear here.
            </p>
          ) : inspectorTab === "review" ? (
            currentSheet.review_items.length === 0 ? (
              <div className="py-10 text-center space-y-2">
                <CheckCircle2 className="w-8 h-8 text-[var(--signal-ok)] mx-auto" />
                <p className="text-sm font-semibold text-[var(--ink-primary)]">
                  All fields verified with high confidence
                </p>
                <p className="text-xs text-[var(--ink-muted)]">
                  Zero ambiguous, multi-marked, or checksum-flagged fields on this sheet.
                </p>
              </div>
            ) : (
              currentSheet.review_items.map((item) => {
                const editKey = `${currentSheet.sheet_id}:${item.field_id}`;
                return (
                  <div
                    key={item.field_id}
                    className="p-3 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-paper)] space-y-2.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <span className="font-mono text-sm font-semibold">{item.field_id}</span>
                        <span className="ml-2 text-[11px] px-1.5 py-0.5 rounded font-mono bg-[var(--signal-warn-bg)] text-[var(--signal-warn)]">
                          {item.reason}
                        </span>
                      </div>
                      <span className="text-xs font-mono text-[var(--ink-muted)]">
                        {(item.confidence * 100).toFixed(0)}%
                      </span>
                    </div>

                    <p className="text-xs text-[var(--ink-secondary)] leading-relaxed flex items-start gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-[var(--signal-warn)] shrink-0 mt-0.5" />
                      <span>{item.message}</span>
                    </p>

                    {item.candidate_options.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {item.candidate_options.map((opt) => (
                          <button
                            key={opt}
                            type="button"
                            onClick={() => onApplyOverride(currentSheet.sheet_id, item.field_id, opt)}
                            className={`px-2.5 py-1 rounded text-xs font-mono font-semibold border transition-colors cursor-pointer ${
                              item.suggested_value === opt
                                ? "bg-[var(--ink-primary)] text-white border-[var(--ink-primary)]"
                                : "bg-white border-[var(--border-strong)] hover:border-[var(--ink-primary)]"
                            }`}
                          >
                            {opt}
                          </button>
                        ))}
                        <button
                          type="button"
                          onClick={() => onApplyOverride(currentSheet.sheet_id, item.field_id, "")}
                          className="px-2.5 py-1 rounded text-xs font-mono border border-[var(--border-strong)] bg-white text-[var(--ink-secondary)] hover:border-[var(--ink-primary)] cursor-pointer"
                        >
                          Blank
                        </button>
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        <input
                          type="text"
                          className="workbench-input flex-1 font-mono text-xs"
                          value={manualEdits[editKey] ?? item.suggested_value}
                          onChange={(e) =>
                            setManualEdits((prev) => ({ ...prev, [editKey]: e.target.value }))
                          }
                        />
                        <button
                          type="button"
                          onClick={() =>
                            onApplyOverride(
                              currentSheet.sheet_id,
                              item.field_id,
                              manualEdits[editKey] ?? item.suggested_value
                            )
                          }
                          className="btn-primary text-xs !py-1"
                        >
                          Confirm
                        </button>
                      </div>
                    )}
                  </div>
                );
              })
            )
          ) : (
            <div className="space-y-3">
              {Object.keys(currentSheet.grouped_values).length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-muted)]">
                    Grouped Identifiers
                  </p>
                  {Object.entries(currentSheet.grouped_values).map(([k, v]) => (
                    <div
                      key={k}
                      className="flex items-center justify-between px-2.5 py-1.5 rounded bg-[var(--surface-subtle)] font-mono text-xs"
                    >
                      <span className="text-[var(--ink-secondary)]">{k}</span>
                      <span className="font-semibold">{v || "—"}</span>
                    </div>
                  ))}
                </div>
              )}

              <input
                type="search"
                placeholder="Filter fields (e.g. q12)..."
                className="workbench-input w-full text-xs"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />

              <div className="divide-y divide-[var(--border-hairline)] border border-[var(--border-hairline)] rounded-lg overflow-hidden">
                {Object.values(currentSheet.fields)
                  .filter((f) => f.field_id.toLowerCase().includes(searchTerm.toLowerCase()))
                  .map((f) => (
                    <div
                      key={f.field_id}
                      className="px-3 py-2 bg-white flex items-center justify-between text-xs gap-2"
                    >
                      <span className="font-mono font-medium w-24 shrink-0">{f.field_id}</span>
                      <span className="font-mono font-semibold text-[var(--ink-primary)]">
                        {f.value || "—"}
                      </span>
                      <span
                        className={`font-mono text-[11px] ${
                          f.status === "ok" || f.status === "blank"
                            ? "text-[var(--signal-ok)]"
                            : f.status === "multi_marked"
                              ? "text-[var(--signal-err)]"
                              : "text-[var(--signal-warn)]"
                        }`}
                      >
                        {(f.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
