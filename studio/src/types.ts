export type RegistrationMode = "aruco" | "markers" | "page_quad" | "homography" | "none";
export type FieldType = "mcq" | "grid_digits" | "grid_alpha" | "custom";
export type BlockDirection = "horizontal" | "vertical";
export type FieldStatus = "ok" | "blank" | "multi_marked" | "low_confidence" | "invalid_checksum";

export interface RegistrationConfig {
  mode: RegistrationMode;
  aruco_dict?: string;
  aruco_ids?: [number, number, number, number];
  target_corners?: [number, number][] | null;
  marker_path?: string | null;
  split_ratio_x?: number;
  split_ratio_y?: number;
  auto_rotate?: boolean;
}

export interface DetectionConfig {
  fill_threshold: number;
  blank_floor: number;
  min_separation: number;
  review_confidence_threshold: number;
  normalize_illumination: boolean;
}

export interface FieldBlock {
  name: string;
  field_type: FieldType;
  direction: BlockDirection;
  origin: [number, number];
  origin_mode: "center" | "top_left";
  bubble_radius: number;
  bubbles_gap: number;
  labels_gap: number;
  options: string[];
  labels: string[];
  allow_multiple?: boolean;
  empty_value?: string;
  group_as?: string | null;
  validator?: "tr_tckn" | "luhn" | "digits" | "non_empty" | null;
}

export interface Template {
  version: string;
  name: string;
  description: string;
  page_width: number;
  page_height: number;
  registration: RegistrationConfig;
  detection: DetectionConfig;
  blocks: FieldBlock[];
  metadata?: Record<string, unknown>;
}

export interface BubbleReading {
  option: string;
  cx: number;
  cy: number;
  radius: number;
  fill_ratio: number;
  darkness: number;
  ink_score: number;
  combined_score: number;
  selected: boolean;
}

export interface FieldReading {
  field_id: string;
  block_name: string;
  value: string;
  selected_options: string[];
  confidence: number;
  status: FieldStatus;
  bubbles: BubbleReading[];
}

export interface ReviewItem {
  field_id: string;
  block_name: string;
  reason: FieldStatus;
  suggested_value: string;
  confidence: number;
  candidate_options: string[];
  bbox: [number, number, number, number];
  message: string;
}

export interface SheetResult {
  sheet_id: string;
  source_file: string;
  page_index: number;
  template_name: string;
  fields: Record<string, FieldReading>;
  grouped_values: Record<string, string>;
  review_items: ReviewItem[];
  overall_confidence: number;
  registration_method: string;
  registration_score: number;
  rotation_applied: number;
  elapsed_ms: number;
  warnings: string[];
  error: string | null;
}

export interface ScanResponse {
  template_name: string;
  total_sheets: number;
  flagged_sheets: number;
  failed_sheets: number;
  total_elapsed_ms: number;
  sheets: SheetResult[];
  overlays: Record<string, string>;
}

export interface IdGridSpec {
  name: string;
  title: string;
  digits: number;
  options: string[];
  validator: "tr_tckn" | "luhn" | "digits" | "non_empty" | null;
}

export interface SheetSpec {
  preset_id: string;
  title: string;
  subtitle: string;
  page_format: "A4" | "LETTER";
  dpi: number;
  num_questions: number;
  options: string[];
  questions_per_column: number;
  include_booklet: boolean;
  booklet_options: string[];
  id_grids: IdGridSpec[];
  question_prefix: string;
}

export interface AnswerKey {
  exam_name: string;
  booklet_field: string | null;
  default_booklet: string;
  booklets: Record<string, Record<string, string | string[]>>;
  answers: Record<string, string | string[]>;
}

export interface GradingPolicy {
  name: string;
  correct_points: number;
  incorrect_points: number;
  blank_points: number;
  partial_credit: boolean;
  bonus_questions: string[];
  sections: unknown[];
}

export interface PresetBundle {
  id: string;
  spec: SheetSpec;
  template: Template;
  sample_answer_key: AnswerKey;
}

export interface PresetsResponse {
  sheet_presets: PresetBundle[];
  grading_policies: GradingPolicy[];
}

export interface GenerateResponse {
  filename: string;
  pdf_base64: string;
  preview_data_url: string;
  template: Template;
  sample_answer_key: AnswerKey;
}

export interface QuestionVerdict {
  question_id: string;
  marked: string;
  expected: string;
  verdict: "correct" | "incorrect" | "blank" | "bonus";
  points: number;
  confidence: number;
}

export interface StudentGrade {
  sheet_id: string;
  source_file: string;
  student_metadata: Record<string, string>;
  booklet: string;
  total_questions: number;
  correct: number;
  incorrect: number;
  blank: number;
  bonus: number;
  raw_score: number;
  max_score: number;
  percentage: number;
  flagged_for_review: boolean;
  verdicts: QuestionVerdict[];
}

export interface ItemPsychometrics {
  question_id: string;
  expected: string;
  attempts: number;
  correct_count: number;
  incorrect_count: number;
  blank_count: number;
  difficulty_p: number;
  discrimination_d: number;
  omit_rate: number;
  option_distribution: Record<string, number>;
  quality_flag: "good" | "too_easy" | "too_hard" | "poor_discrimination";
}

export interface ScoreHistogramBin {
  label: string;
  low: number;
  high: number;
  count: number;
}

export interface ExamAnalytics {
  student_count: number;
  question_count: number;
  mean_score: number;
  median_score: number;
  std_score: number;
  min_score: number;
  max_score: number;
  mean_percentage: number;
  percentiles: Record<string, number>;
  kr20_reliability: number | null;
  histogram: ScoreHistogramBin[];
  items: ItemPsychometrics[];
}

export interface GradingReport {
  exam_name: string;
  policy_name: string;
  grades: StudentGrade[];
  analytics: ExamAnalytics;
}
