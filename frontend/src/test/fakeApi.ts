import { vi } from "vitest";

import type { ExamDetail, Me } from "../api/types";

type Reply = [status: number, body?: unknown];
type Handler = (body: unknown) => Reply;

export interface FakeApi {
  calls: { method: string; path: string; body: unknown; headers: Record<string, string> }[];
  on: (route: string, handler: Handler | Reply) => void;
}

/** Replace fetch with a router: `api.on("GET /api/auth/me", [200, me])`. Unrouted calls 404. */
export function fakeApi(): FakeApi {
  const routes = new Map<string, Handler>();
  const calls: FakeApi["calls"] = [];

  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const path =
        typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const raw = init?.body;
      const body: unknown = typeof raw === "string" && raw.startsWith("{") ? JSON.parse(raw) : raw;
      calls.push({ method, path, body, headers: (init?.headers ?? {}) as Record<string, string> });
      const handler = routes.get(`${method} ${path}`);
      const [status, payload] = handler ? handler(body) : [404, { code: "not_found" }];
      return Promise.resolve(
        status === 204
          ? new Response(null, { status })
          : new Response(JSON.stringify(payload ?? null), {
              status,
              headers: { "Content-Type": "application/json" },
            }),
      );
    }),
  );

  return {
    calls,
    on(route, handler) {
      routes.set(route, typeof handler === "function" ? handler : () => handler);
    },
  };
}

export function me(role: "admin" | "teacher" = "teacher", language: "en" | "fr" = "en"): Me {
  return {
    user: {
      id: 1,
      username: "alice",
      display_name: "Alice Teacher",
      email: null,
      role,
      preferred_language: language,
      is_active: true,
      last_login_at: null,
    },
    school: { id: 1, name: "GBHS Test", country: "Cameroon", curriculum: "cm_gce_ol" },
    csrf_token: "csrf-123",
  };
}

export const SUBJECTS = [
  { code: "chemistry", name_en: "Chemistry", name_fr: "Chimie" },
  { code: "mathematics", name_en: "Mathematics", name_fr: "Mathématiques" },
];

export function examDetail(overrides: Partial<ExamDetail> = {}): ExamDetail {
  return {
    id: 7,
    class_id: 3,
    class_name: "Form 5A",
    subject_code: "chemistry",
    title: "Mock exam 1",
    exam_date: "2026-11-20",
    status: "draft",
    question_count: 1,
    total_marks: 2,
    scripts: { waiting: 0, ai_marked: 0, confirmed: 0 },
    updated_at: "2026-10-14T08:00:00Z",
    questions: [
      {
        id: 11,
        label: "1(a)",
        prompt_text: "State two properties of metals.",
        max_marks: 2,
        points: [
          { id: 21, description: "Conducts electricity", marks: 1, alternatives: ["conductor"] },
          { id: 22, description: "Malleable", marks: 1, alternatives: [] },
        ],
      },
    ],
    validation: { blocking: [], readiness: [], notices: [], is_ready: true },
    ...overrides,
  };
}
