// Shapes returned by the backend API. Keep in sync with backend/app/schemas.

export type Role = "admin" | "teacher";
export type Language = "en" | "fr";
export type ExamStatus = "draft" | "ready" | "marking" | "reviewing" | "completed";

export interface Issue {
  code: string;
  path: (string | number)[];
  params: Record<string, unknown>;
}

export interface User {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  role: Role;
  preferred_language: Language;
  is_active: boolean;
  last_login_at: string | null;
}

export interface School {
  id: number;
  name: string;
  country: string;
  curriculum: string;
}

export interface Me {
  user: User;
  school: School;
  csrf_token: string;
}

export interface SchoolClass {
  id: number;
  name: string;
  academic_year: string;
  teacher_id: number;
  teacher_name: string;
  student_count: number;
}

export interface Student {
  id: number;
  class_id: number;
  code: string;
  display_name: string | null;
  training_consent: boolean;
  consent_recorded_at: string | null;
  consent_recorded_by_id: number | null;
}

export interface Subject {
  code: string;
  name_en: string;
  name_fr: string;
}

export interface PointInput {
  description: string;
  marks: number;
  alternatives: string[];
}

export interface QuestionInput {
  label: string;
  prompt_text: string;
  max_marks: number;
  points: PointInput[];
}

export interface MarkSchemeInput {
  questions: QuestionInput[];
}

export interface ValidationReport {
  blocking: Issue[];
  readiness: Issue[];
  notices: Issue[];
  is_ready: boolean;
}

export interface ExamSummary {
  id: number;
  class_id: number;
  class_name: string;
  subject_code: string;
  title: string;
  exam_date: string | null;
  status: ExamStatus;
  question_count: number;
  total_marks: number;
  scripts: { waiting: number; ai_marked: number; confirmed: number };
  updated_at: string;
}

export interface ExamDetail extends ExamSummary {
  questions: (Omit<QuestionInput, "points"> & {
    id: number;
    points: (PointInput & { id: number })[];
  })[];
  validation: ValidationReport;
}

export interface ImportPreview {
  scheme: MarkSchemeInput | null;
  issues: Issue[];
  validation: ValidationReport | null;
}

export type UploadStatus = "pending" | "processing" | "processed" | "failed";
export type PageState = "assigned" | "unassigned" | "discarded";
export type UnassignedReason =
  | "before_first_cover"
  | "follows_unassigned_cover"
  | "qr_damaged"
  | "qr_unreadable"
  | "qr_conflict"
  | "qr_not_ours"
  | "qr_bad_checksum"
  | "unknown_sheet"
  | "other_exam"
  | "duplicate_in_upload"
  | "already_uploaded"
  | "returned_by_teacher";

export interface CoverSheetRow {
  student_id: number;
  code: string;
  display_name: string | null;
  has_sheet: boolean;
}

export interface Upload {
  id: number;
  original_filename: string;
  sha256: string;
  size_bytes: number;
  page_count: number | null;
  status: UploadStatus;
  error_code: string | null;
  created_at: string;
  processed_at: string | null;
}

export interface ScanPage {
  id: number;
  upload_id: number;
  source_page_index: number;
  is_cover: boolean;
  state: PageState;
  position: number | null;
  unassigned_reason: UnassignedReason | null;
  related_page_id: number | null;
  detected_exam_title: string | null;
  width: number;
  height: number;
}

export interface StudentRef {
  id: number;
  code: string;
  display_name: string | null;
}

export type PageCountFlag = "no_answer_pages" | "more_than_usual" | "fewer_than_usual";

export interface ScriptWithPages {
  id: number;
  student: StudentRef;
  status: string;
  pages: ScanPage[];
  page_count_flag: PageCountFlag | null;
}

export interface ScriptsOverview {
  scripts: ScriptWithPages[];
  typical_page_count: number | null;
  missing: StudentRef[];
}

export interface SystemStatus {
  worker_online: boolean;
  ai_backend: string;
  model_server_reachable: boolean;
  reader_model: string;
  reader_model_installed: boolean;
  marker_model: string;
  marker_model_installed: boolean;
}

export interface AiStatus {
  scripts: Record<string, number>;
  flagged: { script_id: number; student_code: string; reason: string }[];
  jobs_queued: number;
  jobs_running: number;
  jobs_failed: number;
  system: SystemStatus;
}

// --- teacher review (Phase 4) -------------------------------------------------------------

export type ScriptStatus = "waiting" | "transcribed" | "ai_marked" | "in_review" | "confirmed";

export type ErrorCategory =
  "correct" | "conceptual_error" | "language_expression" | "transcription_uncertain" | "omitted";

export const ERROR_CATEGORIES: readonly ErrorCategory[] = [
  "correct",
  "conceptual_error",
  "language_expression",
  "transcription_uncertain",
  "omitted",
];

export type Rotation = 0 | 90 | 180 | 270;

export interface QueueItem {
  script_id: number;
  student_code: string;
  student_name: string | null;
  status: ScriptStatus;
  manual_reason: string | null;
  reviewable: boolean;
  page_count: number;
  page_count_flag: PageCountFlag | null;
  auto_rotated_pages: number;
  min_confidence: number | null;
  uncertain_points: number;
  deductions: number;
  marks_deducted: number;
  decided_points: number;
  total_points: number;
  proposed_total: number | null;
  final_total: number | null;
  max_total: number;
  review_seconds: number | null;
  active_seconds: number | null;
  test_model: boolean;
}

export interface Queue {
  exam_id: number;
  exam_title: string;
  exam_status: ExamStatus;
  items: QueueItem[];
  typical_page_count: number | null;
  confirmed_count: number;
  timed_count: number;
  average_review_seconds: number | null;
  average_active_seconds: number | null;
  test_model_count: number;
}

export interface TranscriptionVersion {
  id: number;
  text: string;
  source: "model" | "teacher";
  model_name: string | null;
  model_version: string | null;
  prompt_version: string | null;
  rotation: number;
  created_at: string;
}

export interface ReviewPage {
  id: number;
  position: number | null;
  is_cover: boolean;
  width: number;
  height: number;
  rotation: number;
  rotation_teacher: number | null;
  rotation_auto: number;
  auto_rotated: boolean;
  auto_rotation_confidence: number | null;
  rotated_after_transcription: boolean;
  retranscribe_pending: boolean;
  transcription: TranscriptionVersion | null;
  versions: TranscriptionVersion[];
  edited_after_marking: boolean;
}

export interface ReviewPoint {
  id: number;
  position: number;
  description: string;
  alternatives: string[];
  max_marks: number;
  decision_id: number | null;
  proposed_marks: number | null;
  evidence: string;
  confidence: number | null;
  error_category: ErrorCategory | null;
  deducted: number;
  final_marks: number | null;
  final_category: ErrorCategory | null;
  decided_at: string | null;
  model_name: string | null;
  model_version: string | null;
  prompt_version: string | null;
}

export interface ReviewQuestion {
  id: number;
  label: string;
  prompt_text: string;
  max_marks: number;
  points: ReviewPoint[];
  comment: string;
  proposed_total: number | null;
  final_total: number | null;
  deductions: number;
  marks_deducted: number;
}

export interface ScriptReview {
  script: {
    id: number;
    status: ScriptStatus;
    manual_reason: string | null;
    student_code: string;
    student_name: string | null;
    reviewed_at: string | null;
    confirmed_at: string | null;
  };
  exam: { id: number; title: string; subject_code: string };
  ready: boolean;
  locked: boolean;
  can_confirm: boolean;
  pages: ReviewPage[];
  questions: ReviewQuestion[];
  totals: {
    max_total: number;
    proposed_total: number | null;
    final_total: number | null;
    decided_points: number;
    total_points: number;
    deductions: number;
    marks_deducted: number;
  };
  navigation: {
    previous_id: number | null;
    next_id: number | null;
    position: number;
    count: number;
  };
  marked_on_earlier_text: boolean;
  // Output from a test model (Mock): never real AI marking.
  test_model: boolean;
  ai_run: number;
}

// --- results and exports (Phase 5) --------------------------------------------------------

export type ExportKind = "csv" | "student_pdf" | "class_pdf" | "dataset";
export type ExportStatus = "pending" | "done" | "failed";

export interface ExportJob {
  id: number;
  kind: ExportKind;
  status: ExportStatus;
  filename: string | null;
  size_bytes: number | null;
  error_code: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface Results {
  exam_id: number;
  exam_title: string;
  exam_status: ExamStatus;
  questions: { id: number; label: string; max_marks: number; average: number | null }[];
  rows: {
    script_id: number;
    student_code: string;
    student_name: string | null;
    status: ScriptStatus;
    confirmed: boolean;
    marks: (number | null)[];
    total: number | null;
    percentage: number | null;
    test_model: boolean;
  }[];
  max_total: number;
  average_total: number | null;
  confirmed_count: number;
  script_count: number;
  timed_count: number;
  average_review_seconds: number | null;
  average_active_seconds: number | null;
  class_pdfs: ExportJob[];
  test_model_count: number;
}

export interface TrainingExport {
  exams: {
    exam_id: number;
    title: string;
    subject_code: string;
    confirmed: number;
    consented: number;
  }[];
  exports: ExportJob[];
}

export interface ModelConfig {
  ai_backend: string;
  model_host: string;
  reader_model: string;
  marker_model: string;
  marker_evidence: string;
  model_timeout_seconds: number;
  model_output_retries: number;
  orientation_check: string;
}
