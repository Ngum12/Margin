import { request } from "./client";
import type {
  AiProgress,
  AiStatus,
  CoverSheetRow,
  ExamDetail,
  ExamStatus,
  ExportJob,
  ExamSummary,
  ErrorCategory,
  ImportPreview,
  Language,
  MarkSchemeInput,
  Me,
  ModelConfig,
  PageCheck,
  Queue,
  RedPen,
  Results,
  Rotation,
  Role,
  SchoolClass,
  ScanPage,
  ScriptReview,
  ScriptsOverview,
  Student,
  Subject,
  SystemStatus,
  TrainingExport,
  Upload,
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

  coverSheets: (examId: number) =>
    request<CoverSheetRow[]>("GET", `/api/exams/${String(examId)}/cover-sheets`),
  prepareCoverSheets: (examId: number) =>
    request<CoverSheetRow[]>("POST", `/api/exams/${String(examId)}/cover-sheets`),
  coverSheetsPdfUrl: (examId: number) => `/api/exams/${String(examId)}/cover-sheets.pdf`,
  uploads: (examId: number) => request<Upload[]>("GET", `/api/exams/${String(examId)}/uploads`),
  uploadScan: (examId: number, file: File) =>
    request<Upload>("POST", `/api/exams/${String(examId)}/uploads`, {
      file,
      contentType: "application/pdf",
      // Headers are ASCII-only; the server decodes this.
      headers: { "X-Filename": encodeURIComponent(file.name) },
    }),
  retryUpload: (uploadId: number) =>
    request<Upload>("POST", `/api/uploads/${String(uploadId)}/retry`),
  originalUrl: (uploadId: number) => `/api/uploads/${String(uploadId)}/original`,
  scripts: (examId: number) =>
    request<ScriptsOverview>("GET", `/api/exams/${String(examId)}/scripts`),
  tray: (examId: number) =>
    request<ScanPage[]>("GET", `/api/exams/${String(examId)}/unassigned-pages`),
  assignPages: (examId: number, pageIds: number[], studentId: number) =>
    request<undefined>("POST", `/api/exams/${String(examId)}/pages/assign`, {
      json: { page_ids: pageIds, student_id: studentId },
    }),
  unassignPages: (examId: number, pageIds: number[]) =>
    request<undefined>("POST", `/api/exams/${String(examId)}/pages/unassign`, {
      json: { page_ids: pageIds },
    }),
  discardPages: (examId: number, pageIds: number[]) =>
    request<undefined>("POST", `/api/exams/${String(examId)}/pages/discard`, {
      json: { page_ids: pageIds },
    }),
  aiStatus: (examId: number) => request<AiStatus>("GET", `/api/exams/${String(examId)}/ai-status`),
  aiProgress: (examId: number) =>
    request<AiProgress>("GET", `/api/exams/${String(examId)}/ai-progress`),
  pageCheck: (examId: number) =>
    request<PageCheck>("GET", `/api/exams/${String(examId)}/page-check`),
  confirmPageCheck: (examId: number) =>
    request<PageCheck>("POST", `/api/exams/${String(examId)}/page-check`),
  startAiMarking: (examId: number) =>
    request<{ scripts_queued: number }>("POST", `/api/exams/${String(examId)}/ai-marking`),
  pageImageUrl: (pageId: number, size: "thumb" | "full" = "thumb") =>
    `/api/pages/${String(pageId)}/image?size=${size}`,

  // Teacher review (Phase 4). Every edit returns the whole updated review.
  queue: (examId: number) => request<Queue>("GET", `/api/exams/${String(examId)}/queue`),
  review: (scriptId: number) =>
    request<ScriptReview>("GET", `/api/scripts/${String(scriptId)}/review`),
  reviewHeartbeat: (scriptId: number) =>
    request<{ session_open: boolean; active_seconds: number }>(
      "POST",
      `/api/scripts/${String(scriptId)}/review-heartbeat`,
    ),
  setDecision: (
    scriptId: number,
    pointId: number,
    data: { marks?: number; category?: ErrorCategory },
  ) =>
    request<ScriptReview>("PUT", `/api/scripts/${String(scriptId)}/decisions/${String(pointId)}`, {
      json: data,
    }),
  acceptPoint: (scriptId: number, pointId: number) =>
    request<ScriptReview>(
      "POST",
      `/api/scripts/${String(scriptId)}/decisions/${String(pointId)}/accept`,
    ),
  acceptAll: (scriptId: number) =>
    request<{ accepted: number; review: ScriptReview }>(
      "POST",
      `/api/scripts/${String(scriptId)}/accept-all`,
    ),
  setComment: (scriptId: number, questionId: number, text: string) =>
    request<ScriptReview>(
      "PUT",
      `/api/scripts/${String(scriptId)}/questions/${String(questionId)}/comment`,
      { json: { text } },
    ),
  redPen: (scriptId: number) => request<RedPen>("GET", `/api/scripts/${String(scriptId)}/red-pen`),
  rerunScript: (scriptId: number) =>
    request<ScriptReview>("POST", `/api/scripts/${String(scriptId)}/rerun-ai`),
  rerunExam: (examId: number) =>
    request<{ scripts_queued: number }>("POST", `/api/exams/${String(examId)}/rerun-ai`),
  confirmScript: (scriptId: number) =>
    request<ScriptReview>("POST", `/api/scripts/${String(scriptId)}/confirm`),
  reopenScript: (scriptId: number) =>
    request<ScriptReview>("POST", `/api/scripts/${String(scriptId)}/reopen`),
  editTranscription: (pageId: number, text: string) =>
    request<ScriptReview>("POST", `/api/pages/${String(pageId)}/transcription`, {
      json: { text },
    }),
  rotatePage: (pageId: number, rotation: Rotation | null) =>
    request<ScriptReview>("POST", `/api/pages/${String(pageId)}/rotation`, {
      json: { rotation },
    }),
  undoAutoRotation: (pageId: number) =>
    request<ScriptReview>("POST", `/api/pages/${String(pageId)}/undo-auto-rotation`),
  retranscribePage: (pageId: number) =>
    request<ScriptReview>("POST", `/api/pages/${String(pageId)}/retranscribe`),

  // Results and exports (Phase 5). Downloads are plain links: same origin, session cookie.
  results: (examId: number) => request<Results>("GET", `/api/exams/${String(examId)}/results`),
  resultsCsvUrl: (examId: number) => `/api/exams/${String(examId)}/results.csv`,
  markedPdfUrl: (scriptId: number) => `/api/scripts/${String(scriptId)}/marked.pdf`,
  requestClassPdf: (examId: number) =>
    request<ExportJob>("POST", `/api/exams/${String(examId)}/exports/class-pdf`),
  exportStatus: (exportId: number) => request<ExportJob>("GET", `/api/exports/${String(exportId)}`),
  exportFileUrl: (exportId: number) => `/api/exports/${String(exportId)}/file`,
  trainingExport: () => request<TrainingExport>("GET", "/api/admin/training-export"),
  requestTrainingExport: (examIds: number[] | null) =>
    request<ExportJob>("POST", "/api/admin/training-export", { json: { exam_ids: examIds } }),
  modelConfig: () => request<ModelConfig>("GET", "/api/admin/model-config"),
  systemStatus: () => request<SystemStatus>("GET", "/api/system/status"),

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
