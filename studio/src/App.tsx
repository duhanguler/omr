import { useEffect, useState } from "react";
import {
  BarChart3,
  Camera,
  ExternalLink,
  Grid,
  Printer,
  ScanLine,
  Sparkles,
} from "lucide-react";
import { fetchPresets, loadDemoCohort } from "./api/client";
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
  const [tab, setTab] = useState<ActiveTab>("scan");
  const [presets, setPresets] = useState<PresetBundle[]>([]);
  const [policies, setPolicies] = useState<GradingPolicy[]>([]);
  const [activeTemplate, setActiveTemplate] = useState<Template | null>(null);
  const [activeAnswerKey, setActiveAnswerKey] = useState<AnswerKey | null>(null);
  const [scanResponse, setScanResponse] = useState<ScanResponse | null>(null);
  const [gradingReport, setGradingReport] = useState<GradingReport | null>(null);
  const [loadingDemo, setLoadingDemo] = useState(false);

  useEffect(() => {
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
    try {
      const demo = await loadDemoCohort("quick_quiz_20");
      setActiveTemplate(demo.template);
      setActiveAnswerKey(demo.answer_key);
      setScanResponse(demo.scan_response);
      setGradingReport(demo.grading_report);
      setTab("scan");
    } finally {
      setLoadingDemo(false);
    }
  }

  function handleCameraCapture(sheet: SheetResult, overlayUrl?: string) {
    setScanResponse((prev) => {
      const prevSheets = prev?.sheets ?? [];
      const prevOverlays = prev?.overlays ?? {};
      const nextSheets = [sheet, ...prevSheets];
      const nextOverlays = overlayUrl ? { ...prevOverlays, [sheet.sheet_id]: overlayUrl } : prevOverlays;
      return {
        template_name: sheet.template_name,
        total_sheets: nextSheets.length,
        flagged_sheets: nextSheets.filter((s) => s.review_items.length > 0).length,
        failed_sheets: nextSheets.filter((s) => s.error !== null).length,
        total_elapsed_ms: (prev?.total_elapsed_ms ?? 0) + sheet.elapsed_ms,
        sheets: nextSheets,
        overlays: nextOverlays,
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
        if (fieldId in fields) {
          fields[fieldId] = {
            ...fields[fieldId],
            value,
            selected_options: value ? value.split("") : [],
            confidence: 1.0,
            status: value ? "ok" : "blank",
          };
        } else if (fieldId in grouped) {
          grouped[fieldId] = value;
        }
        return {
          ...sheet,
          fields,
          grouped_values: grouped,
          review_items: sheet.review_items.filter((item) => item.field_id !== fieldId),
        };
      });
      return {
        ...prev,
        sheets: updatedSheets,
        flagged_sheets: updatedSheets.filter((s) => s.review_items.length > 0).length,
      };
    });
  }

  const totalFlags =
    scanResponse?.sheets.reduce((acc, s) => acc + s.review_items.length, 0) ?? 0;

  const navItems: { id: ActiveTab; label: string; icon: typeof ScanLine; badge?: number }[] = [
    { id: "scan", label: "Scan & Review", icon: ScanLine, badge: totalFlags > 0 ? totalFlags : undefined },
    { id: "camera", label: "Live Camera", icon: Camera },
    { id: "designer", label: "Template Designer", icon: Grid },
    { id: "generator", label: "Sheet Generator", icon: Printer },
    { id: "analytics", label: "Grading & Analytics", icon: BarChart3 },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-20 bg-[var(--surface-card)]/95 backdrop-blur border-b border-[var(--border-hairline)]">
        <div className="max-w-[1440px] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 shrink-0">
            <svg width="26" height="26" viewBox="0 0 28 28" fill="none" aria-hidden="true">
              <rect x="2" y="2" width="24" height="24" rx="6" fill="#14181F" />
              <circle cx="14" cy="14" r="6.5" stroke="#FAF9F6" strokeWidth="1.8" />
              <circle cx="14" cy="14" r="2.7" fill="#0F8A5F" />
            </svg>
            <div className="leading-tight">
              <h1 className="text-sm font-bold tracking-tight text-[var(--ink-primary)]">
                OMRKit Studio
              </h1>
              <p className="text-[11px] font-mono text-[var(--ink-muted)]">v2.1 · Optical Workbench</p>
            </div>
          </div>

          <nav className="flex items-center gap-1 overflow-x-auto" aria-label="Workspace navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = tab === item.id;
              return (
                <button
                  key={item.id}
                  id={`nav-${item.id}`}
                  type="button"
                  onClick={() => setTab(item.id)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium inline-flex items-center gap-1.5 whitespace-nowrap transition-colors cursor-pointer ${
                    active
                      ? "bg-[var(--ink-primary)] text-white"
                      : "text-[var(--ink-secondary)] hover:bg-[var(--surface-subtle)] hover:text-[var(--ink-primary)]"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{item.label}</span>
                  {item.badge !== undefined && (
                    <span className="ml-0.5 px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-amber-500 text-white">
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          <div className="flex items-center gap-2 shrink-0">
            <button
              id="try-demo-btn"
              type="button"
              disabled={loadingDemo}
              onClick={() => void handleRunDemo()}
              className="btn-secondary !py-1.5 !px-2.5 text-xs"
            >
              <Sparkles className="w-3.5 h-3.5 text-[var(--signal-ok)]" />
              <span>{loadingDemo ? "Loading..." : "Try Demo"}</span>
            </button>

            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="hidden xl:inline-flex items-center gap-1 text-xs font-mono text-[var(--ink-secondary)] hover:text-[var(--ink-primary)]"
            >
              API <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-[1440px] w-full mx-auto px-4 sm:px-6 py-5">
        {tab === "scan" && (
          <ScanWorkspace
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
            activeTemplate={activeTemplate}
            onSheetCaptured={handleCameraCapture}
            onGoToReview={() => setTab("scan")}
          />
        )}

        {tab === "designer" && (
          <TemplateDesigner
            activeTemplate={activeTemplate}
            onUseTemplate={(tmpl) => {
              setActiveTemplate(tmpl);
              setTab("scan");
            }}
          />
        )}

        {tab === "generator" && (
          <SheetGenerator
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
            sheets={scanResponse?.sheets ?? []}
            policies={policies}
            answerKey={activeAnswerKey}
            onUpdateAnswerKey={setActiveAnswerKey}
            report={gradingReport}
            onReportReady={setGradingReport}
          />
        )}
      </main>
    </div>
  );
}
