import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AiStatus, ScanPage } from "../api/types";
import en from "../i18n/locales/en.json";
import fr from "../i18n/locales/fr.json";
import { examDetail, fakeApi, me, quietQueueExtras, SUBJECTS } from "../test/fakeApi";
import { renderApp } from "../test/render";

const STUDENTS = [
  { student_id: 1, code: "AAAAAA", display_name: "Ama Fon", has_sheet: true },
  { student_id: 2, code: "BBBBBB", display_name: null, has_sheet: true },
];

function trayPage(overrides: Partial<ScanPage>): ScanPage {
  return {
    id: 1,
    upload_id: 5,
    source_page_index: 0,
    is_cover: false,
    state: "unassigned",
    position: null,
    unassigned_reason: "before_first_cover",
    related_page_id: null,
    detected_exam_title: null,
    width: 1654,
    height: 2339,
    ...overrides,
  };
}

function aiStatus(overrides: Partial<AiStatus> = {}): AiStatus {
  return {
    scripts: { waiting: 2, transcribed: 0, ai_marked: 0, in_review: 0, confirmed: 0 },
    flagged: [],
    jobs_queued: 0,
    jobs_running: 0,
    jobs_failed: 0,
    system: {
      worker_online: true,
      ai_backend: "ollama",
      model_server_reachable: true,
      reader_model: "qwen3-vl:8b-instruct",
      reader_model_installed: true,
      marker_model: "qwen3-vl:8b-instruct",
      marker_model_installed: true,
    },
    ...overrides,
  };
}

function setup(language: "en" | "fr" = "en") {
  const api = fakeApi();
  api.on("GET /api/auth/me", [200, me("teacher", language)]);
  api.on("GET /api/subjects", [200, SUBJECTS]);
  api.on("GET /api/exams/7", [200, examDetail({ status: "ready" })]);
  api.on("GET /api/exams/7/cover-sheets", [200, STUDENTS]);
  api.on("GET /api/exams/7/ai-status", [200, aiStatus()]);
  quietQueueExtras(api);
  api.on("GET /api/exams/7/queue", [
    200,
    {
      exam_id: 7,
      exam_title: "Mock exam 1",
      exam_status: "marking",
      items: [],
      typical_page_count: null,
      confirmed_count: 0,
      timed_count: 0,
      average_review_seconds: null,
      average_active_seconds: null,
    },
  ]);
  api.on("GET /api/exams/7/uploads", [
    200,
    [
      {
        id: 5,
        original_filename: "form5a.pdf",
        sha256: "ab",
        size_bytes: 10,
        page_count: 4,
        status: "processed",
        error_code: null,
        created_at: "2026-10-14T08:00:00Z",
        processed_at: "2026-10-14T08:01:00Z",
      },
    ],
  ]);
  api.on("GET /api/exams/7/scripts", [
    200,
    {
      scripts: [],
      typical_page_count: null,
      missing: [
        { id: 1, code: "AAAAAA", display_name: "Ama Fon" },
        { id: 2, code: "BBBBBB", display_name: null },
      ],
    },
  ]);
  api.on("GET /api/exams/7/unassigned-pages", [
    200,
    [
      trayPage({
        id: 10,
        source_page_index: 1,
        is_cover: true,
        unassigned_reason: "other_exam",
        detected_exam_title: "Economics mock",
      }),
      trayPage({
        id: 11,
        source_page_index: 2,
        unassigned_reason: "follows_unassigned_cover",
        related_page_id: 10,
      }),
      trayPage({ id: 12, source_page_index: 3, unassigned_reason: "qr_damaged", is_cover: true }),
    ],
  ]);
  return api;
}

describe("scans screen", () => {
  it("shows uploads, translated tray reasons and missing students", async () => {
    setup();
    renderApp("/exams/7/scans");

    expect(await screen.findByText("form5a.pdf")).toBeInTheDocument();
    const upload = screen.getByRole("row", { name: /form5a\.pdf/ });
    expect(within(upload).getByText(en.scans.uploadStatus.processed)).toBeInTheDocument();
    expect(
      screen.getByText(/Cover sheet from another exam \(Economics mock\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(en.scans.reason.qr_damaged)).toBeInTheDocument();
    expect(screen.getByText("Unassigned pages: 3")).toBeInTheDocument();
    expect(screen.getByText(/AAAAAA \(Ama Fon\), BBBBBB/)).toBeInTheDocument();
  });

  it("uploads a PDF as application/pdf with the encoded file name and CSRF token", async () => {
    const api = setup();
    api.on("POST /api/exams/7/uploads", [202, { id: 6, status: "pending" }]);
    const user = userEvent.setup();
    renderApp("/exams/7/scans");

    const file = new File(["%PDF-1.7"], "Form 5A — lot 1.pdf", { type: "application/pdf" });
    await user.upload(await screen.findByLabelText(en.scans.choose), file);

    await waitFor(() => {
      expect(api.calls.some((c) => c.method === "POST" && c.path === "/api/exams/7/uploads")).toBe(
        true,
      );
    });
    const call = api.calls.find((c) => c.method === "POST" && c.path === "/api/exams/7/uploads");
    expect(call?.headers["Content-Type"]).toBe("application/pdf");
    expect(call?.headers["X-Filename"]).toBe(encodeURIComponent("Form 5A — lot 1.pdf"));
    expect(call?.headers["X-CSRF-Token"]).toBe("csrf-123");
    expect(call?.body).toBe(file);
  });

  it("selecting a problem cover selects its following pages, then assigns them", async () => {
    const api = setup();
    api.on("POST /api/exams/7/pages/assign", [204]);
    const user = userEvent.setup();
    renderApp("/exams/7/scans");

    const coverCard = (await screen.findByText(/another exam/)).closest("li");
    if (!coverCard) throw new Error("cover card not found");
    await user.click(within(coverCard).getByRole("checkbox"));
    await user.selectOptions(screen.getByLabelText(en.scans.assignTo), "2");
    await user.click(screen.getByRole("button", { name: "Assign selected (2)" }));

    await waitFor(() => {
      expect(api.calls.some((c) => c.path === "/api/exams/7/pages/assign")).toBe(true);
    });
    expect(api.calls.find((c) => c.path === "/api/exams/7/pages/assign")?.body).toEqual({
      page_ids: [10, 11],
      student_id: 2,
    });
  });

  it("shows a plain-language reason for a failed upload, in French", async () => {
    const api = setup("fr");
    api.on("GET /api/exams/7/uploads", [
      200,
      [
        {
          id: 5,
          original_filename: "abime.pdf",
          sha256: "ab",
          size_bytes: 10,
          page_count: null,
          status: "failed",
          error_code: "upload.pdf_unreadable",
          created_at: "2026-10-14T08:00:00Z",
          processed_at: null,
        },
      ],
    ]);
    renderApp("/exams/7/scans");

    expect(await screen.findByText(fr.errors.upload.pdf_unreadable)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: fr.scans.retry })).toBeInTheDocument();
  });
});

describe("page count check", () => {
  it("asks the teacher to check a script with unusually many pages", async () => {
    const api = setup();
    const page = trayPage({ state: "assigned", unassigned_reason: null });
    const student = (id: number, code: string) => ({ id, code, display_name: null });
    api.on("GET /api/exams/7/scripts", [
      200,
      {
        scripts: [
          {
            id: 1,
            student: student(1, "AAAAAA"),
            status: "waiting",
            pages: Array(8).fill(page),
            page_count_flag: "more_than_usual",
          },
          {
            id: 2,
            student: student(2, "BBBBBB"),
            status: "waiting",
            pages: Array(3).fill(page),
            page_count_flag: null,
          },
        ],
        typical_page_count: 3,
        missing: [],
      },
    ]);
    renderApp("/exams/7/scans");

    expect(
      await screen.findByText(
        "Check: more pages than usual (typical: 3). Another student's pages may have been added.",
      ),
    ).toBeInTheDocument();
  });
});

describe("AI marking panel (marking queue screen)", () => {
  it("starts AI marking with the CSRF token", async () => {
    const api = setup();
    api.on("POST /api/exams/7/ai-marking", [202, { scripts_queued: 2 }]);
    const user = userEvent.setup();
    renderApp("/exams/7/queue");

    await user.click(await screen.findByRole("button", { name: en.ai.start }));

    await waitFor(() => {
      expect(api.calls.some((c) => c.path === "/api/exams/7/ai-marking")).toBe(true);
    });
    const call = api.calls.find((c) => c.path === "/api/exams/7/ai-marking");
    expect(call?.headers["X-CSRF-Token"]).toBe("csrf-123");
  });

  it("explains when the worker or the model is not available", async () => {
    const api = setup();
    const status = aiStatus();
    api.on("GET /api/exams/7/ai-status", [
      200,
      aiStatus({
        system: { ...status.system, worker_online: false, reader_model_installed: false },
      }),
    ]);
    renderApp("/exams/7/queue");

    expect(await screen.findByText(en.ai.workerOffline)).toBeInTheDocument();
    expect(
      screen.getByText("The AI model qwen3-vl:8b-instruct is not installed on the model server."),
    ).toBeInTheDocument();
  });

  it("lists scripts flagged for manual marking, in French", async () => {
    const api = setup("fr");
    api.on("GET /api/exams/7/ai-status", [
      200,
      aiStatus({
        flagged: [{ script_id: 1, student_code: "AAAAAA", reason: "ai.reader_invalid_output" }],
      }),
    ]);
    renderApp("/exams/7/queue");

    expect(await screen.findByText(fr.ai.flaggedTitle)).toBeInTheDocument();
    expect(
      screen.getByText(new RegExp(fr.ai.manualReason.ai.reader_invalid_output)),
    ).toBeInTheDocument();
  });
});

describe("cover sheets screen", () => {
  it("prepares sheets and offers the PDF download", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me()]);
    api.on("GET /api/exams/7", [200, examDetail({ status: "ready" })]);
    api.on("GET /api/exams/7/cover-sheets", [
      200,
      STUDENTS.map((s) => ({ ...s, has_sheet: false })),
    ]);
    api.on("POST /api/exams/7/cover-sheets", [200, STUDENTS]);
    const user = userEvent.setup();
    renderApp("/exams/7/sheets");

    await user.click(
      await screen.findByRole("button", { name: "Prepare cover sheets (2 to create)" }),
    );

    const link = await screen.findByRole("link", { name: en.sheets.download });
    expect(link).toHaveAttribute("href", "/api/exams/7/cover-sheets.pdf");
    expect(screen.getByText("Ama Fon")).toBeInTheDocument();
  });

  it("explains that a draft exam must be marked ready first", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me()]);
    api.on("GET /api/exams/7", [200, examDetail({ status: "draft" })]);
    api.on("GET /api/exams/7/cover-sheets", [200, []]);
    renderApp("/exams/7/sheets");

    expect(await screen.findByText(en.sheets.needReady)).toBeInTheDocument();
  });
});
