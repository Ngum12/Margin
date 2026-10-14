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
