import { useEffect, useState } from "react";
import {
  BarChart3,
  Camera,
  ExternalLink,
  Globe,
  Grid,
  Play,
  Printer,
  ScanLine,
  X,
} from "lucide-react";
import { fetchHealth, fetchPresets, loadDemoCohort, type HealthResponse } from "./api/client";
import { DICTIONARIES, LOCALE_OPTIONS, detectInitialLocale, type Locale } from "./i18n";
import type {
  AnswerKey,
  GradingPolicy,
  GradingReport,
  PresetBundle,
  ScanResponse,
  SheetResult,
  Template,
} from "./types";
import { AnalyticsView } from "./views/AnalyticsView";
import { CameraScanner } from "./views/CameraScanner";
import { ScanWorkspace } from "./views/ScanWorkspace";
import { SheetGenerator } from "./views/SheetGenerator";
import { TemplateDesigner } from "./views/TemplateDesigner";

type ActiveTab = "scan" | "camera" | "designer" | "generator" | "analytics";

export default function App() {
  const [locale, setLocale] = useState<Locale>(detectInitialLocale);
  const [tab, setTab] = useState<ActiveTab>("scan");
  const [presets, setPresets] = useState<PresetBundle[]>([]);
  const [policies, setPolicies] = useState<GradingPolicy[]>([]);
  const [activeTemplate, setActiveTemplate] = useState<Template | null>(null);
  const [activeAnswerKey, setActiveAnswerKey] = useState<AnswerKey | null>(null);
  const [scanResponse, setScanResponse] = useState<ScanResponse | null>(null);
  const [gradingReport, setGradingReport] = useState<GradingReport | null>(null);
  const [loadingDemo, setLoadingDemo] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [demoBannerDismissed, setDemoBannerDismissed] = useState(false);

  const t = DICTIONARIES[locale];

  function handleChangeLocale(next: Locale) {
    setLocale(next);
    document.documentElement.lang = next;
    try {
      window.localStorage.setItem("omrkit_locale", next);
    } catch {
      // ignore storage restriction
    }
  }

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => {
        // Ignore if static preview
      });
    fetchPresets()
      .then((res) => {
        setPresets(res.sheet_presets);
        setPolicies(res.grading_policies);
        const defaultPreset =
          res.sheet_presets.find((p) => p.id === "standard_mcq_40") ?? res.sheet_presets[0];
        if (defaultPreset) {
          setActiveTemplate(defaultPreset.template);
          setActiveAnswerKey(defaultPreset.sample_answer_key);
        }
      })
      .catch(() => {
        // API may not be reachable during static preview
      });
  }, []);

  async function handleRunDemo() {
    setLoadingDemo(true);
    setDemoError(null);
    try {
      const demo = await loadDemoCohort("quick_quiz_20");
      setActiveTemplate(demo.template);
      setActiveAnswerKey(demo.answer_key);
      setScanResponse(demo.scan_response);
      setGradingReport(demo.grading_report);
      setTab("scan");
    } catch (err) {
      setDemoError(
        err instanceof Error
          ? `Could not load sample cohort: ${err.message}`
          : "Could not load sample cohort. Please try again."
      );
    } finally {
      setLoadingDemo(false);
    }
  }

  function handleCameraCapture(
    sheet: SheetResult,
    overlayUrl?: string,
    crops?: Record<string, string>,
    dims?: [number, number]
  ) {
    setScanResponse((prev) => {
      const prevSheets = prev?.sheets ?? [];
      const prevOverlays = prev?.overlays ?? {};
      const prevCrops = prev?.review_crops ?? {};
      const prevDims = prev?.sheet_dimensions ?? {};
      const nextSheets = [sheet, ...prevSheets];
      return {
        template_name: sheet.template_name,
        total_sheets: nextSheets.length,
        flagged_sheets: nextSheets.filter((s) => s.review_items.length > 0).length,
        failed_sheets: nextSheets.filter((s) => s.error !== null).length,
        total_elapsed_ms: (prev?.total_elapsed_ms ?? 0) + sheet.elapsed_ms,
        sheets: nextSheets,
        overlays: overlayUrl ? { ...prevOverlays, [sheet.sheet_id]: overlayUrl } : prevOverlays,
        review_crops: crops ? { ...prevCrops, [sheet.sheet_id]: crops } : prevCrops,
        sheet_dimensions: dims ? { ...prevDims, [sheet.sheet_id]: dims } : prevDims,
      };
    });
    setGradingReport(null);
  }

  function handleApplyOverride(sheetId: string, fieldId: string, value: string) {
    setScanResponse((prev) => {
      if (!prev) return prev;
      const updatedSheets = prev.sheets.map((sheet) => {
        if (sheet.sheet_id !== sheetId) return sheet;
        const fields = { ...sheet.fields };
        const grouped = { ...sheet.grouped_values };
        let overallConfidence = sheet.overall_confidence;
        if (fieldId in fields) {
          const prevField = fields[fieldId];
          const validOpts = new Set(prevField.bubbles.map((b) => b.option));
          const selectedOpts = !value
            ? []
            : validOpts.has(value)
              ? [value]
              : value.split("");
          const selectedSet = new Set(selectedOpts);
          fields[fieldId] = {
            ...prevField,
            value,
            selected_options: selectedOpts,
            confidence: 1.0,
            status: value ? "ok" : "blank",
            bubbles: prevField.bubbles.map((b) => ({
              ...b,
              selected: selectedSet.has(b.option),
            })),
          };
          const fieldList = Object.values(fields);
          if (fieldList.length > 0) {
            const avg =
              fieldList.reduce((sum, f) => sum + f.confidence, 0) / fieldList.length;
            overallConfidence = Math.round(avg * 10000) / 10000;
          }
        } else if (fieldId in grouped) {
          grouped[fieldId] = value;
        }
        return {
          ...sheet,
          fields,
          grouped_values: grouped,
          overall_confidence: overallConfidence,
          review_items: sheet.review_items.filter((item) => item.field_id !== fieldId),
        };
      });
      return {
        ...prev,
        sheets: updatedSheets,
        flagged_sheets: updatedSheets.filter((s) => s.review_items.length > 0).length,
      };
    });
    setGradingReport(null);
  }

  const totalFlags =
    scanResponse?.sheets.reduce((acc, s) => acc + s.review_items.length, 0) ?? 0;

  const navItems: { id: ActiveTab; label: string; icon: typeof ScanLine; badge?: number }[] = [
    { id: "scan", label: t.navScan, icon: ScanLine, badge: totalFlags > 0 ? totalFlags : undefined },
    { id: "camera", label: t.navCamera, icon: Camera },
    { id: "designer", label: t.navDesigner, icon: Grid },
    { id: "generator", label: t.navGenerator, icon: Printer },
    { id: "analytics", label: t.navAnalytics, icon: BarChart3 },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top Instrument Bar */}
      <header className="sticky top-0 z-20 bg-[var(--surface-card)] border-b border-[var(--border-hairline)]">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 h-13 flex items-center justify-between gap-4">
          {/* Geometric Optical Fiducial Mark + Title */}
          <div className="flex items-center gap-2.5 shrink-0">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect x="1.5" y="1.5" width="21" height="21" rx="3" stroke="#111317" strokeWidth="1.5" />
              <path d="M5 12H8M16 12H19M12 5V8M12 16V19" stroke="#111317" strokeWidth="1.3" />
              <circle cx="12" cy="12" r="2.6" fill="#0D7A52" />
            </svg>
            <div className="leading-none">
              <h1 className="text-[13px] font-bold tracking-tight text-[var(--ink-primary)]">
                OMRKit
              </h1>
              <p className="text-[10px] font-mono text-[var(--ink-muted)] mt-0.5">
                v{health?.version ?? "2.2.0"} · {t.subtitle}
              </p>
            </div>
          </div>

          {/* Crisp Architectural Underline Navigation */}
          <nav
            className="flex items-stretch h-13 gap-1 overflow-x-auto"
            aria-label="Workspace navigation"
          >
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  id={`nav-${item.id}`}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`px-3 border-b-2 text-xs font-medium inline-flex items-center gap-1.5 whitespace-nowrap transition-colors cursor-pointer ${
                    active
                      ? "border-[var(--ink-primary)] text-[var(--ink-primary)] font-semibold"
                      : "border-transparent text-[var(--ink-secondary)] hover:text-[var(--ink-primary)] hover:border-[var(--border-strong)]"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{item.label}</span>
                  {item.badge !== undefined && (
                    <span className="ml-0.5 px-1.5 py-0.5 rounded-[3px] text-[10px] leading-none font-mono bg-[var(--signal-warn-bg)] text-[var(--signal-warn)] border border-amber-300">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          {/* Right Utility Strip: Sample Loader + Locale Selector + OpenAPI */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              id="try-demo-btn"
              type="button"
              disabled={loadingDemo}
              onClick={() => void handleRunDemo()}
              className="btn-secondary !py-1.5 !px-2.5 text-xs"
            >
              <Play className="w-3 h-3 fill-current text-[var(--signal-ok)]" />
              <span>{loadingDemo ? t.loading : t.loadSample}</span>
            </button>

            <label className="inline-flex items-center gap-1 px-2 py-1 rounded-[5px] border border-[var(--border-strong)] bg-[var(--surface-card)] text-xs font-mono">
              <Globe className="w-3 h-3 text-[var(--ink-muted)]" />
              <select
                id="locale-select"
                aria-label="Interface language"
                value={locale}
                onChange={(e) => handleChangeLocale(e.target.value as Locale)}
                className="bg-transparent text-xs font-mono text-[var(--ink-primary)] focus:outline-none cursor-pointer"
              >
                {LOCALE_OPTIONS.map((opt) => (
                  <option key={opt.code} value={opt.code}>
                    {opt.short} · {opt.native}
                  </option>
                ))}
              </select>
            </label>

            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="hidden xl:inline-flex items-center gap-1 px-2 py-1 text-xs font-mono text-[var(--ink-secondary)] hover:text-[var(--ink-primary)]"
            >
              API <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </header>

      {health?.demo_mode && !demoBannerDismissed && (
        <div className="bg-[var(--surface-subtle)] border-b border-[var(--border-hairline)]">
          <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-1.5 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex flex-wrap items-center gap-2 text-[var(--ink-secondary)]">
              <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[var(--ink-primary)]">
                {t.demoNoticeTitle}
              </span>
              <span className="text-[var(--border-strong)]">|</span>
              <span>
                {t.demoNoticeBody} ({health.limits.max_upload_mb} MB · {health.limits.max_files_per_scan}{" "}
                files max)
              </span>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                disabled={loadingDemo}
                onClick={() => void handleRunDemo()}
                className="font-mono text-xs font-medium text-[var(--accent-cobalt)] hover:underline cursor-pointer"
              >
                {t.demoLoadLink} →
              </button>
              <button
                type="button"
                aria-label="Dismiss notice"
                onClick={() => setDemoBannerDismissed(true)}
                className="text-[var(--ink-muted)] hover:text-[var(--ink-primary)] cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {demoError && (
        <div className="bg-[var(--signal-err-bg)] border-b border-red-200">
          <div className="max-w-[1440px] mx-auto px-4 sm:px-6 py-2 flex items-center justify-between gap-2 text-xs text-[var(--signal-err)]">
            <span className="font-mono">{demoError}</span>
            <button
              type="button"
              aria-label="Dismiss error"
              onClick={() => setDemoError(null)}
              className="hover:opacity-75 cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      <main className="flex-1 max-w-[1440px] w-full mx-auto px-4 sm:px-6 py-5">
        {tab === "scan" && (
          <ScanWorkspace
            t={t}
            presets={presets}
            activeTemplate={activeTemplate}
            onSelectTemplate={(tmpl) => {
              setActiveTemplate(tmpl);
              const matched = presets.find((p) => p.template.name === tmpl.name);
              if (matched) setActiveAnswerKey(matched.sample_answer_key);
            }}
            scanResponse={scanResponse}
            onScanComplete={(res) => {
              setScanResponse(res);
              setGradingReport(null);
            }}
            onApplyOverride={handleApplyOverride}
            onProceedToGrading={() => setTab("analytics")}
          />
        )}

        {tab === "camera" && (
          <CameraScanner
            t={t}
            activeTemplate={activeTemplate}
            onSheetCaptured={handleCameraCapture}
            onGoToReview={() => setTab("scan")}
          />
        )}

        {tab === "designer" && (
          <TemplateDesigner
            t={t}
            activeTemplate={activeTemplate}
            onUseTemplate={(tmpl) => {
              setActiveTemplate(tmpl);
              setTab("scan");
            }}
          />
        )}

        {tab === "generator" && (
          <SheetGenerator
            t={t}
            presets={presets}
            onActivateGenerated={(tmpl, key) => {
              setActiveTemplate(tmpl);
              setActiveAnswerKey(key);
              setTab("scan");
            }}
          />
        )}

        {tab === "analytics" && (
          <AnalyticsView
            t={t}
            sheets={scanResponse?.sheets ?? []}
            policies={policies}
            answerKey={activeAnswerKey}
            onUpdateAnswerKey={setActiveAnswerKey}
            report={gradingReport}
            onReportReady={setGradingReport}
          />
        )}
      </main>

      {/* Compact Hardware-Grade Telemetry Footer */}
      <footer className="border-t border-[var(--border-hairline)] bg-[var(--surface-card)]">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 h-8 flex items-center justify-between gap-4 text-[11px] font-mono text-[var(--ink-muted)] overflow-x-auto whitespace-nowrap">
          <div className="flex items-center gap-3">
            <span>OMRKit v{health?.version ?? "2.2.0"}</span>
            {activeTemplate && (
              <>
                <span className="text-[var(--border-strong)]">/</span>
                <span>
                  {activeTemplate.name} ({activeTemplate.page_width}×{activeTemplate.page_height}px ·{" "}
                  {activeTemplate.registration.mode})
                </span>
              </>
            )}
          </div>
          <div className="flex items-center gap-3">
            {scanResponse && (
              <span>
                {scanResponse.total_sheets} sheets · {totalFlags} flagged ·{" "}
                {scanResponse.total_elapsed_ms.toFixed(0)}ms
              </span>
            )}
            <a
              href="https://github.com/duhanguler/omr"
              target="_blank"
              rel="noreferrer"
              className="hover:text-[var(--ink-primary)]"
            >
              github.com/duhanguler/omr
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
