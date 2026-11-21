import { useEffect, useRef, useState } from "react";
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
import type { Dictionary } from "../i18n";
import type { PresetBundle, ReviewItem, ScanResponse, SheetResult, Template } from "../types";

interface ScanWorkspaceProps {
  t: Dictionary;
  presets: PresetBundle[];
  activeTemplate: Template | null;
  onSelectTemplate: (template: Template) => void;
  scanResponse: ScanResponse | null;
  onScanComplete: (response: ScanResponse) => void;
  onApplyOverride: (sheetId: string, fieldId: string, value: string) => void;
  onProceedToGrading: () => void;
}

export function ScanWorkspace({
  t,
  presets,
  activeTemplate,
  onSelectTemplate,
  scanResponse,
  onScanComplete,
  onApplyOverride,
  onProceedToGrading,
}: ScanWorkspaceProps) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [autoDetectQr, setAutoDetectQr] = useState<boolean>(false);
  const [activeSheetId, setActiveSheetId] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<"review" | "all">("review");
  const [zoomMode, setZoomMode] = useState<"fit" | number>("fit");
  const [activeReviewIdx, setActiveReviewIdx] = useState<number>(0);
  const [hoveredReviewField, setHoveredReviewField] = useState<string | null>(null);
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
  const currentCrops = currentSheet ? scanResponse?.review_crops?.[currentSheet.sheet_id] : undefined;
  const currentDims =
    (currentSheet ? scanResponse?.sheet_dimensions?.[currentSheet.sheet_id] : undefined) ??
    (activeTemplate ? [activeTemplate.page_width, activeTemplate.page_height] : undefined);

  const reviewItems = currentSheet?.review_items ?? [];
  const clampedReviewIdx =
    reviewItems.length > 0 ? Math.min(activeReviewIdx, reviewItems.length - 1) : 0;
  const highlightedReview: ReviewItem | null =
    inspectorTab === "review"
      ? reviewItems.find((r) => r.field_id === hoveredReviewField) ??
        reviewItems[clampedReviewIdx] ??
        null
      : null;

  // Keyboard speed-triage when reviewing flagged HITL items
  useEffect(() => {
    if (!currentSheet || inspectorTab !== "review" || reviewItems.length === 0) return;

    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")
      ) {
        return;
      }
      const item = reviewItems[clampedReviewIdx];
      if (!item || !currentSheet) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveReviewIdx((i) => Math.min(reviewItems.length - 1, i + 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveReviewIdx((i) => Math.max(0, i - 1));
        return;
      }
      if (item.candidate_options.length === 0) return;

      if (e.key === "Backspace") {
        e.preventDefault();
        onApplyOverride(currentSheet.sheet_id, item.field_id, "");
        return;
      }
      if (e.key === "Enter" && item.suggested_value) {
        e.preventDefault();
        onApplyOverride(currentSheet.sheet_id, item.field_id, item.suggested_value);
        return;
      }
      const upper = e.key.toUpperCase();
      if (item.candidate_options.includes(upper)) {
        e.preventDefault();
        onApplyOverride(currentSheet.sheet_id, item.field_id, upper);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [clampedReviewIdx, currentSheet, inspectorTab, onApplyOverride, reviewItems]);

  async function handleRunScan() {
    if (!autoDetectQr && !activeTemplate) {
      setError("Please select a template or enable QR Auto-Detect.");
      return;
    }
    if (selectedFiles.length === 0) {
      setError("Please drop or choose at least one image or PDF file.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await scanFiles(selectedFiles, autoDetectQr ? "auto" : activeTemplate!);
      onScanComplete(response);
      if (response.sheets.length > 0) {
        const firstFlagged = response.sheets.find((s) => s.review_items.length > 0);
        const initial = firstFlagged ?? response.sheets[0];
        setActiveSheetId(initial.sheet_id);
        setActiveReviewIdx(0);
        setInspectorTab(initial.review_items.length > 0 ? "review" : "all");
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
      setAutoDetectQr(false);
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
  const numericZoom = zoomMode === "fit" ? 100 : zoomMode;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
      {/* Left Control Rail */}
      <aside className="lg:col-span-3 space-y-3.5">
        <section className="paper-card p-3.5 space-y-2.5">
          <div className="flex items-center justify-between">
            <h2 className="section-label">{t.activeTemplate}</h2>
            <button
              type="button"
              onClick={() => templateInputRef.current?.click()}
              className="text-xs font-mono text-[var(--accent-cobalt)] hover:underline cursor-pointer"
            >
              {t.uploadJson}
            </button>
            <input
              ref={templateInputRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleTemplateUpload(file);
                e.target.value = "";
              }}
            />
          </div>

          <select
            id="scan-template-select"
            className="workbench-input w-full"
            value={
              autoDetectQr
                ? "__auto__"
                : presets.some((p) => p.template.name === activeTemplate?.name)
                  ? activeTemplate?.name ?? ""
                  : "__custom__"
            }
            onChange={(e) => {
              if (e.target.value === "__auto__") {
                setAutoDetectQr(true);
                return;
              }
              setAutoDetectQr(false);
              const found = presets.find((p) => p.template.name === e.target.value);
              if (found) onSelectTemplate(found.template);
            }}
          >
            <option value="__auto__">{t.autoDetectQr}</option>
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
            <div className="text-[11px] text-[var(--ink-muted)] font-mono flex flex-wrap gap-x-2.5 gap-y-0.5 pt-0.5">
              <span>
                {activeTemplate.page_width}×{activeTemplate.page_height}px
              </span>
              <span>mode:{activeTemplate.registration.mode}</span>
              <span>{activeTemplate.blocks.length} blk</span>
            </div>
          )}
        </section>

        <section className="paper-card p-3.5 space-y-2.5">
          <h2 className="section-label">{t.opticalSheets}</h2>

          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const dropped = Array.from(e.dataTransfer.files);
              if (dropped.length) setSelectedFiles(dropped);
            }}
            onClick={() => fileInputRef.current?.click()}
            className="border border-dashed border-[var(--border-strong)] rounded-[5px] p-4 text-center cursor-pointer hover:bg-[var(--surface-subtle)] transition-colors"
          >
            <Upload className="w-4 h-4 mx-auto mb-1.5 text-[var(--ink-secondary)]" />
            <p className="text-xs font-medium text-[var(--ink-primary)]">{t.dropSheetsTitle}</p>
            <p className="text-[11px] text-[var(--ink-muted)] mt-0.5">{t.dropSheetsSub}</p>
            <input
              ref={fileInputRef}
              id="scan-files-input"
              type="file"
              multiple
              accept="image/*,.pdf"
              className="hidden"
              onChange={(e) => {
                if (e.target.files) setSelectedFiles(Array.from(e.target.files));
                e.target.value = "";
              }}
            />
          </div>

          {selectedFiles.length > 0 && (
            <ul className="text-[11px] space-y-1 max-h-28 overflow-y-auto">
              {selectedFiles.map((f) => (
                <li
                  key={`${f.name}-${f.size}`}
                  className="flex items-center justify-between px-2 py-1 rounded-[4px] bg-[var(--surface-subtle)] font-mono"
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
            <div className="text-xs p-2.5 rounded-[4px] bg-[var(--signal-err-bg)] text-[var(--signal-err)] border border-red-200 font-mono">
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
            <ScanLine className="w-3.5 h-3.5" />
            {loading
              ? t.scanning
              : `${t.scanAction}${selectedFiles.length > 0 ? ` (${selectedFiles.length})` : ""}`}
          </button>
        </section>

        {sheets.length > 0 && (
          <section className="paper-card p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <h2 className="section-label">
                {t.scannedBatch} ({sheets.length})
              </h2>
              <span className="text-[11px] font-mono text-[var(--ink-muted)]">
                {scanResponse?.total_elapsed_ms.toFixed(0)} ms
              </span>
            </div>
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {sheets.map((s) => {
                const active = s.sheet_id === currentSheet?.sheet_id;
                return (
                  <button
                    key={s.sheet_id}
                    type="button"
                    onClick={() => {
                      setActiveSheetId(s.sheet_id);
                      setActiveReviewIdx(0);
                      setHoveredReviewField(null);
                    }}
                    className={`w-full text-left px-2.5 py-1.5 rounded-[4px] border text-xs transition-colors cursor-pointer ${
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
                        <span className="px-1.5 py-0.5 rounded-[3px] bg-[var(--signal-warn-bg)] text-[var(--signal-warn)] font-mono text-[10px]">
                          {s.review_items.length}
                        </span>
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5 text-[var(--signal-ok)] shrink-0" />
                      )}
                    </div>
                    <div className="text-[10px] text-[var(--ink-muted)] mt-0.5 font-mono">
                      {s.error
                        ? t.alignmentFailed
                        : `${(s.overall_confidence * 100).toFixed(1)}% · ${s.registration_method} · ${s.elapsed_ms.toFixed(0)}ms`}
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="pt-2 border-t border-[var(--border-hairline)] flex flex-col gap-2">
              <div className="grid grid-cols-2 gap-1.5">
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
                {t.gradeAndAnalyze} ({sheets.length}) <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </section>
        )}
      </aside>

      {/* Center Annotated Sheet Viewport with Live Optical Reticle */}
      <section className="lg:col-span-5 paper-card overflow-hidden">
        <div className="px-3.5 py-2.5 border-b border-[var(--border-hairline)] flex items-center justify-between gap-2 bg-[var(--surface-card)]">
          <div className="min-w-0">
            <h2 className="text-xs font-semibold text-[var(--ink-primary)] truncate">
              {currentSheet ? currentSheet.source_file : t.opticalCanvasTitle}
            </h2>
            <p className="text-[11px] text-[var(--ink-muted)] font-mono truncate">
              {currentSheet
                ? `reg:${currentSheet.registration_method} (${(currentSheet.registration_score * 100).toFixed(0)}%) · rot:${currentSheet.rotation_applied}° · conf:${(currentSheet.overall_confidence * 100).toFixed(1)}%`
                : t.opticalCanvasSub}
            </p>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={() => setZoomMode("fit")}
              className={`px-2 py-1 rounded-[4px] border text-[11px] font-mono cursor-pointer ${
                zoomMode === "fit"
                  ? "bg-[var(--ink-primary)] text-white border-[var(--ink-primary)]"
                  : "bg-white border-[var(--border-strong)] text-[var(--ink-secondary)] hover:bg-[var(--surface-subtle)]"
              }`}
            >
              {t.fitBtn}
            </button>
            <button
              type="button"
              onClick={() => setZoomMode(Math.max(50, numericZoom - 25))}
              className="btn-secondary !px-1.5 !py-1"
              title="Zoom out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-[11px] font-mono w-10 text-center text-[var(--ink-secondary)]">
              {zoomMode === "fit" ? "FIT" : `${zoomMode}%`}
            </span>
            <button
              type="button"
              onClick={() => setZoomMode(Math.min(200, numericZoom + 25))}
              className="btn-secondary !px-1.5 !py-1"
              title="Zoom in"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="optical-stage min-h-[540px] max-h-[75vh] overflow-auto flex items-start justify-center p-4">
          {currentSheet?.error ? (
            <div className="my-auto max-w-md text-center space-y-2 p-5 paper-card">
              <XCircle className="w-7 h-7 text-[var(--signal-err)] mx-auto" />
              <p className="text-sm font-semibold">{t.alignmentFailed}</p>
              <p className="text-xs text-[var(--ink-secondary)] font-mono">{currentSheet.error}</p>
            </div>
          ) : currentOverlay ? (
            <div
              className="relative inline-block shrink-0"
              style={{ width: zoomMode === "fit" ? "100%" : `${zoomMode}%` }}
            >
              <img
                src={currentOverlay}
                alt={`Annotated scan of ${currentSheet?.source_file}`}
                className="block w-full h-auto rounded-[3px] border border-[var(--border-strong)] bg-white"
              />
              {/* Precision SVG BBox Reticle targeting active HITL review item */}
              {highlightedReview && currentDims && (
                <svg
                  viewBox={`0 0 ${currentDims[0]} ${currentDims[1]}`}
                  className="pointer-events-none absolute inset-0 w-full h-full"
                  aria-hidden="true"
                >
                  {(() => {
                    const [x1, y1, x2, y2] = highlightedReview.bbox;
                    const bw = Math.max(20, x2 - x1);
                    const bh = Math.max(20, y2 - y1);
                    const tick = Math.min(18, Math.max(10, Math.min(bw, bh) * 0.3));
                    return (
                      <g>
                        <rect
                          x={x1}
                          y={y1}
                          width={bw}
                          height={bh}
                          fill="rgba(24, 73, 198, 0.12)"
                          stroke="#1849C6"
                          strokeWidth={4}
                        />
                        <path
                          d={`M ${x1 - 8} ${y1 + tick} V ${y1 - 8} H ${x1 + tick} M ${x2 - tick} ${y1 - 8} H ${x2 + 8} V ${y1 + tick} M ${x1 - 8} ${y2 - tick} V ${y2 + 8} H ${x1 + tick} M ${x2 - tick} ${y2 + 8} H ${x2 + 8} V ${y2 - tick}`}
                          fill="none"
                          stroke="#111317"
                          strokeWidth={4}
                        />
                      </g>
                    );
                  })()}
                </svg>
              )}
            </div>
          ) : (
            <div className="my-auto text-center max-w-xs space-y-2 text-[var(--ink-muted)]">
              <FileUp className="w-7 h-7 mx-auto opacity-50" />
              <p className="text-xs font-semibold uppercase tracking-wider font-mono text-[var(--ink-secondary)]">
                {t.noSheetTitle}
              </p>
              <p className="text-xs leading-relaxed">{t.noSheetSub}</p>
            </div>
          )}
        </div>
      </section>

      {/* Right HITL Review Queue & Readings Inspector */}
      <section className="lg:col-span-4 paper-card overflow-hidden">
        <div className="border-b border-[var(--border-hairline)] flex">
          <button
            type="button"
            onClick={() => setInspectorTab("review")}
            className={`flex-1 py-2.5 px-3 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
              inspectorTab === "review"
                ? "border-[var(--ink-primary)] text-[var(--ink-primary)]"
                : "border-transparent text-[var(--ink-muted)] hover:text-[var(--ink-primary)]"
            }`}
          >
            {t.reviewQueue} ({currentSheet?.review_items.length ?? totalFlags})
          </button>
          <button
            type="button"
            onClick={() => setInspectorTab("all")}
            className={`flex-1 py-2.5 px-3 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
              inspectorTab === "all"
                ? "border-[var(--ink-primary)] text-[var(--ink-primary)]"
                : "border-transparent text-[var(--ink-muted)] hover:text-[var(--ink-primary)]"
            }`}
          >
            {t.allReadings} ({currentSheet ? Object.keys(currentSheet.fields).length : 0})
          </button>
        </div>

        {inspectorTab === "review" && reviewItems.length > 0 && (
          <div className="px-3.5 py-2 border-b border-[var(--border-hairline)] bg-[var(--surface-paper)] flex items-center justify-between text-[11px] font-mono text-[var(--ink-muted)]">
            <span>{t.kbdHint}</span>
            <span>
              {clampedReviewIdx + 1}/{reviewItems.length}
            </span>
          </div>
        )}

        <div className="p-3.5 max-h-[70vh] overflow-y-auto space-y-2.5">
          {!currentSheet ? (
            <p className="text-xs text-[var(--ink-muted)] py-10 text-center font-mono">
              {t.noSheetTitle}
            </p>
          ) : inspectorTab === "review" ? (
            reviewItems.length === 0 ? (
              <div className="py-10 text-center space-y-1.5">
                <CheckCircle2 className="w-7 h-7 text-[var(--signal-ok)] mx-auto" />
                <p className="text-sm font-semibold text-[var(--ink-primary)]">
                  {t.allVerifiedTitle}
                </p>
                <p className="text-xs text-[var(--ink-muted)] max-w-xs mx-auto">
                  {t.allVerifiedSub}
                </p>
              </div>
            ) : (
              reviewItems.map((item, idx) => {
                const editKey = `${currentSheet.sheet_id}:${item.field_id}`;
                const isActive = idx === clampedReviewIdx;
                const cropUrl = currentCrops?.[item.field_id];
                return (
                  <div
                    key={item.field_id}
                    onClick={() => setActiveReviewIdx(idx)}
                    onMouseEnter={() => setHoveredReviewField(item.field_id)}
                    onMouseLeave={() => setHoveredReviewField(null)}
                    className={`p-3 rounded-[5px] border space-y-2.5 transition-colors cursor-pointer ${
                      isActive
                        ? "border-[var(--ink-primary)] bg-[var(--surface-card)]"
                        : "border-[var(--border-hairline)] bg-[var(--surface-paper)] hover:border-[var(--border-strong)]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-bold text-[var(--ink-primary)]">
                          {item.field_id}
                        </span>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-[3px] font-mono ${
                            item.reason === "multi_marked"
                              ? "bg-[var(--signal-err-bg)] text-[var(--signal-err)]"
                              : "bg-[var(--signal-warn-bg)] text-[var(--signal-warn)]"
                          }`}
                        >
                          {item.reason}
                        </span>
                      </div>
                      <span className="text-xs font-mono text-[var(--ink-muted)]">
                        {(item.confidence * 100).toFixed(0)}%
                      </span>
                    </div>

                    {/* Zoomed Optical Bubble-Strip Evidence Crop */}
                    {cropUrl && (
                      <div className="rounded-[4px] border border-[var(--border-strong)] bg-white p-1 overflow-hidden">
                        <img
                          src={cropUrl}
                          alt={`Zoomed crop of ${item.field_id}`}
                          className="w-full max-h-20 object-contain mx-auto"
                        />
                      </div>
                    )}

                    <p className="text-[11px] text-[var(--ink-secondary)] leading-relaxed flex items-start gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 text-[var(--signal-warn)] shrink-0 mt-0.5" />
                      <span>{item.message}</span>
                    </p>

                    {item.candidate_options.length > 0 ? (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {item.candidate_options.map((opt) => (
                          <button
                            key={opt}
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onApplyOverride(currentSheet.sheet_id, item.field_id, opt);
                            }}
                            className={`px-2.5 py-1 rounded-[4px] text-xs font-mono font-semibold border transition-colors cursor-pointer ${
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
                          onClick={(e) => {
                            e.stopPropagation();
                            onApplyOverride(currentSheet.sheet_id, item.field_id, "");
                          }}
                          className="px-2.5 py-1 rounded-[4px] text-xs font-mono border border-[var(--border-strong)] bg-white text-[var(--ink-secondary)] hover:border-[var(--ink-primary)] cursor-pointer inline-flex items-center gap-1"
                        >
                          {t.blankBtn}
                          {isActive && <span className="kbd-cap">⌫</span>}
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
                          onClick={(e) => {
                            e.stopPropagation();
                            onApplyOverride(
                              currentSheet.sheet_id,
                              item.field_id,
                              manualEdits[editKey] ?? item.suggested_value
                            );
                          }}
                          className="btn-primary text-xs !py-1"
                        >
                          {t.confirmBtn}
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
                  <p className="section-label">{t.groupedIdentifiers}</p>
                  {Object.entries(currentSheet.grouped_values).map(([k, v]) => (
                    <div
                      key={k}
                      className="flex items-center justify-between px-2.5 py-1.5 rounded-[4px] bg-[var(--surface-subtle)] font-mono text-xs"
                    >
                      <span className="text-[var(--ink-secondary)]">{k}</span>
                      <span className="font-semibold">{v || "—"}</span>
                    </div>
                  ))}
                </div>
              )}

              <input
                type="search"
                placeholder={t.filterFields}
                className="workbench-input w-full text-xs"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />

              <div className="divide-y divide-[var(--border-hairline)] border border-[var(--border-hairline)] rounded-[5px] overflow-hidden">
                {Object.values(currentSheet.fields)
                  .filter((f) => f.field_id.toLowerCase().includes(searchTerm.toLowerCase()))
                  .map((f) => (
                    <div
                      key={f.field_id}
                      className="px-3 py-1.5 bg-white flex items-center justify-between text-xs gap-2"
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
