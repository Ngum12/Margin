import { request } from "./client";
import type {
  ExamDetail,
  ExamStatus,
  ExamSummary,
  ImportPreview,
  Language,
  MarkSchemeInput,
  Me,
  Role,
  SchoolClass,
  Student,
  Subject,
  User,
} from "./types";

export const api = {
  login: (username: string, password: string) =>
    request<Me>("POST", "/api/auth/login", { json: { username, password } }),
  logout: () => request<undefined>("POST", "/api/auth/logout"),
  me: () => request<Me>("GET", "/api/auth/me"),
  setLanguage: (preferred_language: Language) =>
    request<Me>("PUT", "/api/auth/me/language", { json: { preferred_language } }),

  subjects: () => request<Subject[]>("GET", "/api/subjects"),

  exams: () => request<ExamSummary[]>("GET", "/api/exams"),
  exam: (id: number) => request<ExamDetail>("GET", `/api/exams/${String(id)}`),
  createExam: (data: {
    class_id: number;
    subject_code: string;
    title: string;
    exam_date: string | null;
  }) => request<ExamDetail>("POST", "/api/exams", { json: data }),
  updateExam: (
    id: number,
    data: Partial<{ title: string; subject_code: string; exam_date: string | null }>,
  ) => request<ExamDetail>("PATCH", `/api/exams/${String(id)}`, { json: data }),
  saveMarkScheme: (id: number, scheme: MarkSchemeInput) =>
    request<ExamDetail>("PUT", `/api/exams/${String(id)}/mark-scheme`, { json: scheme }),
  setExamStatus: (id: number, status: ExamStatus) =>
    request<ExamDetail>("PUT", `/api/exams/${String(id)}/status`, { json: { status } }),
  deleteExam: (id: number) => request<undefined>("DELETE", `/api/exams/${String(id)}`),
  previewImport: (csv: string) =>
    request<ImportPreview>("POST", "/api/mark-scheme/import-preview", {
      text: csv,
      contentType: "text/csv",
    }),

  classes: () => request<SchoolClass[]>("GET", "/api/classes"),
  createClass: (data: { name: string; academic_year: string; teacher_id: number }) =>
    request<SchoolClass>("POST", "/api/classes", { json: data }),
  updateClass: (
    id: number,
    data: Partial<{ name: string; academic_year: string; teacher_id: number }>,
  ) => request<SchoolClass>("PATCH", `/api/classes/${String(id)}`, { json: data }),
  students: (classId: number) =>
    request<Student[]>("GET", `/api/classes/${String(classId)}/students`),
  addStudents: (classId: number, names: string[]) =>
    request<Student[]>("POST", `/api/classes/${String(classId)}/students`, { json: { names } }),
  updateStudent: (id: number, data: { display_name?: string; class_id?: number }) =>
    request<Student>("PATCH", `/api/students/${String(id)}`, { json: data }),
  setConsent: (id: number, training_consent: boolean) =>
    request<Student>("PUT", `/api/students/${String(id)}/consent`, { json: { training_consent } }),

  users: () => request<User[]>("GET", "/api/users"),
  createUser: (data: {
    username: string;
    display_name: string;
    password: string;
    role: Role;
    preferred_language: Language;
  }) => request<User>("POST", "/api/users", { json: data }),
  updateUser: (
    id: number,
    data: Partial<{
      display_name: string;
      role: Role;
      is_active: boolean;
      preferred_language: Language;
    }>,
  ) => request<User>("PATCH", `/api/users/${String(id)}`, { json: data }),
  resetPassword: (id: number, password: string) =>
    request<undefined>("POST", `/api/users/${String(id)}/password`, { json: { password } }),
};
