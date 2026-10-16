import { ApiError } from "./client";

let csrf: string | null = null;
export interface StudentMe {
  idle_minutes?: number;
  code: string;
  name: string | null;
  must_change_pin: boolean;
  csrf_token: string;
}
export interface Remark {
  id: number;
  script_id: number;
  exam_id?: number;
  question_id: number;
  reason: string;
  message: string;
  page_id: number | null;
  location: { x: number; y: number } | null;
  status: string;
  escalated_once: boolean;
  awaiting_hod: boolean;
  unread: boolean;
  responses: {
    automatic: boolean;
    code?: string;
    total?: number;
    message?: string;
    changed?: boolean;
    old_marks?: number;
    new_marks?: number;
    at: string;
  }[];
}
export interface StudentExam {
  id: number;
  exam_id: number;
  title: string;
  subject: string;
  date: string;
  total: number;
  maximum: number;
  class_average?: number | null;
  visibility: string;
  released_at: string;
  remark_days: number;
  remark_max: number;
  escalation: boolean;
  pages: { id: number; position: number; rotation: number }[];
  questions: {
    id: number;
    label: string;
    prompt: string;
    marks: number;
    maximum: number;
    comment: string;
    feedback: { category: string; evidence: string; pages: number[] }[];
    scheme: { description: string; marks: number; alternatives: string[]; rules: object }[];
  }[];
  remarks: Remark[];
}
export interface Overlay {
  pages: {
    page_id: number;
    marks: { kind: string; x: number; y: number; size: number; text: string }[];
  }[];
}
export async function studentRequest<T>(path: string, method = "GET", json?: unknown): Promise<T> {
  const response = await fetch(`/api/student/${path}`, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": csrf } : {}) },
    ...(json === undefined ? {} : { body: JSON.stringify(json) }),
  });
  if (!response.ok) {
    const body = (await response.json()) as { code?: string };
    throw new ApiError(response.status, body.code ?? "error");
  }
  if (response.status === 204) return undefined as T;
  const data = (await response.json()) as T;
  if (
    data &&
    typeof data === "object" &&
    "csrf_token" in data &&
    typeof data.csrf_token === "string"
  )
    csrf = data.csrf_token;
  return data;
}
