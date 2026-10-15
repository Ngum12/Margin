import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AiProgress, PageCheck, Queue } from "../api/types";
import en from "../i18n/locales/en.json";
import { fakeApi, me } from "../test/fakeApi";
import { renderApp } from "../test/render";

function queue(): Queue {
  return {
    exam_id: 7,
    exam_title: "Mock exam 1",
    exam_status: "marking",
    items: [
      {
        script_id: 5,
        student_code: "AAAAAA",
        student_name: "Ama Fon",
        status: "waiting",
        manual_reason: null,
        reviewable: false,
        page_count: 3,
        page_count_flag: null,
        auto_rotated_pages: 0,
        min_confidence: null,
        uncertain_points: 0,
        deductions: 0,
        marks_deducted: 0,
        decided_points: 0,
        total_points: 3,
        proposed_total: null,
        final_total: null,
        max_total: 3,
        review_seconds: null,
        active_seconds: null,
        test_model: false,
      },
    ],
    typical_page_count: null,
    confirmed_count: 0,
    timed_count: 0,
    average_review_seconds: null,
    average_active_seconds: null,
    test_model_count: 0,
  };
}

function pageCheck(overrides: Partial<PageCheck> = {}): PageCheck {
  return {
    exam_id: 7,
    checked_at: null,
    scripts: [
      {
        script_id: 5,
        student_code: "AAAAAA",
        student_name: "Ama Fon",
        status: "waiting",
        pages: [
          {
            id: 31,
            position: 0,
            is_cover: true,
            width: 1654,
            height: 2339,
            rotation: 0,
            rotation_teacher: null,
          },
          {
            id: 32,
            position: 1,
            is_cover: false,
            width: 1654,
            height: 2339,
            rotation: 180,
            rotation_teacher: null,
          },
        ],
      },
    ],
    ...overrides,
  };
}

function progress(overrides: Partial<AiProgress> = {}): AiProgress {
  return {
    running: false,
    percent: 0,
    done_units: 0,
    total_units: 4,
    eta_seconds: null,
    ready: 0,
    manual: 0,
    current_student: null,
    current_page_id: null,
    latest_read: null,
    scripts: [
      { script_id: 5, student_code: "AAAAAA", state: "idle", step: null, index: null, total: null },
    ],
    ...overrides,
  };
}

const AI_STATUS = {
  scripts: { waiting: 1 },
  flagged: [],
  jobs_queued: 0,
  jobs_running: 0,
  jobs_failed: 0,
  system: {
    worker_online: true,
    ai_backend: "ollama",
    model_server_reachable: true,
    reader_model: "qwen3-vl:4b-instruct",
    reader_model_installed: true,
    marker_model: "qwen3-vl:4b-instruct",
    marker_model_installed: true,
  },
};

function setup(check: PageCheck, live: AiProgress = progress()) {
  const api = fakeApi();
  api.on("GET /api/auth/me", [200, me()]);
  api.on("GET /api/exams/7/queue", [200, queue()]);
  api.on("GET /api/exams/7/ai-status", [200, AI_STATUS]);
  api.on("GET /api/exams/7/page-check", [200, check]);
  api.on("GET /api/exams/7/ai-progress", [200, live]);
  return api;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("check pages before AI marking (owner, 2026-10-15)", () => {
  it("keeps AI marking off until the pages are checked, then allows it", async () => {
    const api = setup(pageCheck());
    api.on("POST /api/pages/32/rotation", [200, null]);
    api.on("POST /api/exams/7/page-check", [
      200,
      pageCheck({ checked_at: "2026-10-15T09:00:00Z" }),
    ]);
    const user = userEvent.setup();
    renderApp("/exams/7/queue");

    expect(await screen.findByText(en.pageCheck.firstNotice)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.ai.start })).toBeDisabled();
    // The upside-down page shows as it currently is, and turns with one click.
    const thumb = screen.getByAltText("AAAAAA, page 2");
    expect(thumb).toHaveStyle({ transform: "rotate(180deg)" });
    await user.click(screen.getByRole("button", { name: "Turn AAAAAA page 2 right" }));
    await waitFor(() => {
      const call = api.calls.find((c) => c.path === "/api/pages/32/rotation");
      expect(call?.body).toEqual({ rotation: 270 });
    });

    await user.click(screen.getByRole("button", { name: en.pageCheck.confirm }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: en.ai.start })).toBeEnabled();
    });
    expect(screen.queryByText(en.pageCheck.firstNotice)).not.toBeInTheDocument();
    expect(screen.getByText(/^Checked /)).toBeInTheDocument();
  });
});

describe("live AI progress (owner, 2026-10-15)", () => {
  it("shows the bar, the current step, the time left and the page being read", async () => {
    setup(
      pageCheck({ checked_at: "2026-10-15T09:00:00Z" }),
      progress({
        running: true,
        percent: 54,
        done_units: 2,
        eta_seconds: 540,
        current_student: "AAAAAA",
        current_page_id: 32,
        latest_read: {
          page_id: 31,
          student_code: "AAAAAA",
          text: "1(a) An element is…",
          at: "2026-10-15T09:01:00Z",
        },
        scripts: [
          {
            script_id: 5,
            student_code: "AAAAAA",
            state: "working",
            step: "marking",
            index: 3,
            total: 6,
          },
        ],
      }),
    );
    renderApp("/exams/7/queue");

    const bar = await screen.findByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "54");
    expect(screen.getByText(/Marking AAAAAA, question 3 of 6/)).toBeInTheDocument();
    expect(screen.getByText("about 9 minutes left")).toBeInTheDocument();
    expect(screen.getByAltText("Reading now: AAAAAA")).toHaveAttribute(
      "src",
      "/api/pages/32/image?size=thumb",
    );
    expect(screen.getByText("1(a) An element is…")).toBeInTheDocument();
    const row = screen.getAllByRole("row").find((r) => within(r).queryByText("AAAAAA"));
    expect(row).toBeDefined();
    if (row) expect(within(row).getByText("Marking question 3 of 6…")).toBeInTheDocument();
  });

  it("says when it is finished, in the message and the tab title", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = setup(
      pageCheck({ checked_at: "2026-10-15T09:00:00Z" }),
      progress({ running: true, percent: 90, eta_seconds: 30 }),
    );
    renderApp("/exams/7/queue");
    expect(await screen.findByText("less than a minute left")).toBeInTheDocument();

    api.on("GET /api/exams/7/ai-progress", [
      200,
      progress({ running: false, percent: 100, ready: 1 }),
    ]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3500);
    });

    expect(await screen.findByText(en.progress.finished)).toBeInTheDocument();
    expect(screen.getByText("Ready to review: 1 · Need manual marking: 0")).toBeInTheDocument();
    expect(document.title).toBe("✓ 1 ready · Margin");
  });
});
