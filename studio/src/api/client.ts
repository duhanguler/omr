import type {
  AnswerKey,
  GenerateResponse,
  GradingPolicy,
  GradingReport,
  PresetsResponse,
  ScanResponse,
  SheetResult,
  SheetSpec,
  StudentGrade,
  Template,
} from "../types";

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const parsed = JSON.parse(text) as { detail?: string };
      if (parsed.detail) {
        msg = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
      }
    } catch {
      // keep raw text
    }
    throw new Error(msg || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  demo_mode: boolean;
  limits: {
    max_upload_mb: number;
    max_files_per_scan: number;
    max_pdf_pages: number;
  };
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch("/api/health");
  return handleJson<HealthResponse>(res);
}

export async function fetchPresets(): Promise<PresetsResponse> {
  const res = await fetch("/api/presets");
  return handleJson<PresetsResponse>(res);
}

export async function generateSheet(
  spec: SheetSpec,
  signal?: AbortSignal
): Promise<GenerateResponse> {
  const res = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
    signal,
  });
  return handleJson<GenerateResponse>(res);
}

export async function downloadGeneratedBundle(spec: SheetSpec): Promise<Blob> {
  const res = await fetch("/api/generate/bundle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
  if (!res.ok) throw new Error(`Failed to download bundle (${res.status})`);
  return res.blob();
}

export async function previewUploadedDocument(
  file: File
): Promise<{ filename: string; width: number; height: number; image_data_url: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/preview-image", { method: "POST", body: form });
  return handleJson(res);
}

export async function autoDetectTemplateLayout(file: File): Promise<{
  template: Template;
  detected_bubbles: number;
  blocks_count: number;
  fields_count: number;
  image_data_url: string;
}> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/templates/auto-detect", { method: "POST", body: form });
  return handleJson(res);
}

export async function migrateLegacyTemplate(
  legacyTemplate: Record<string, unknown>,
  name: string
): Promise<{ template: Template }> {
  const res = await fetch("/api/templates/migrate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, legacy_template: legacyTemplate }),
  });
  return handleJson(res);
}

export async function validateTemplate(template: Template): Promise<{
  valid: boolean;
  fields_count: number;
  blocks_count: number;
  preview_bubbles: {
    block: string;
    field_id: string;
    option: string;
    cx: number;
    cy: number;
    radius: number;
  }[];
}> {
  const res = await fetch("/api/templates/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(template),
  });
  return handleJson(res);
}

export async function scanFiles(files: File[], template: Template | "auto"): Promise<ScanResponse> {
  const form = new FormData();
  for (const f of files) {
    form.append("files", f);
  }
  form.append("template_json", template === "auto" ? "auto" : JSON.stringify(template));
  form.append("include_overlay", "true");
  const res = await fetch("/api/scan", { method: "POST", body: form });
  return handleJson<ScanResponse>(res);
}

export async function loadDemoCohort(presetId = "quick_quiz_20"): Promise<{
  template: Template;
  answer_key: AnswerKey;
  scan_response: ScanResponse;
  grading_report: GradingReport;
}> {
  const res = await fetch(`/api/demo/cohort?preset_id=${encodeURIComponent(presetId)}`, {
    method: "POST",
  });
  return handleJson(res);
}

export async function gradeSheets(
  sheets: SheetResult[],
  answerKey: AnswerKey,
  policy: GradingPolicy
): Promise<GradingReport> {
  const res = await fetch("/api/grade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sheets, answer_key: answerKey, policy }),
  });
  return handleJson<GradingReport>(res);
}

export async function exportReportFile(
  format: "csv" | "xlsx" | "moodle" | "canvas" | "scorecards-pdf",
  sheets: SheetResult[],
  report: GradingReport | null
): Promise<Blob> {
  const res = await fetch(`/api/export/${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sheets, report }),
  });
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const parsed = JSON.parse(text) as { detail?: string };
      if (parsed.detail) msg = parsed.detail;
    } catch {
      // keep raw text
    }
    throw new Error(msg || `Export failed (${res.status})`);
  }
  return res.blob();
}

export async function exportStudentScorecard(grade: StudentGrade, examName: string): Promise<Blob> {
  const res = await fetch("/api/export/scorecard", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grade, exam_name: examName }),
  });
  if (!res.ok) throw new Error(`Scorecard export failed (${res.status})`);
  return res.blob();
}

export async function generateRosterPacket(
  spec: SheetSpec,
  rosterCsv: string,
  preFillId: boolean
): Promise<{ blob: Blob; studentCount: number }> {
  const form = new FormData();
  form.append("spec_json", JSON.stringify(spec));
  form.append("roster_csv", rosterCsv);
  form.append("pre_fill_id", String(preFillId));
  const res = await fetch("/api/generate/roster-packet", { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try {
      const parsed = JSON.parse(text) as { detail?: string };
      if (parsed.detail) msg = parsed.detail;
    } catch {
      // keep raw
    }
    throw new Error(msg || `Roster packet generation failed (${res.status})`);
  }
  const studentCount = Number(res.headers.get("X-OMRKit-Student-Count") ?? "0") || 0;
  return { blob: await res.blob(), studentCount };
}

export interface ExtractedKeyResponse {
  answer_key: AnswerKey;
  booklets_detected: string[];
  questions_count: number;
  blank_questions: string[];
  multi_answer_questions: string[];
  warnings: string[];
}

export async function extractAnswerKeyFromSheets(
  files: File[],
  template: Template | "auto",
  examName = "Scanned Answer Key"
): Promise<ExtractedKeyResponse> {
  const form = new FormData();
  for (const f of files) {
    form.append("files", f);
  }
  form.append("template_json", template === "auto" ? "auto" : JSON.stringify(template));
  form.append("exam_name", examName);
  const res = await fetch("/api/answer-key/from-sheet", { method: "POST", body: form });
  return handleJson<ExtractedKeyResponse>(res);
}

export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
