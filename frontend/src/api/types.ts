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
