import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Queue, RedPen, ReviewPoint, ScriptReview } from "../api/types";
import en from "../i18n/locales/en.json";
import fr from "../i18n/locales/fr.json";
import { at } from "../test/at";
import { fakeApi, me, quietQueueExtras } from "../test/fakeApi";
import { renderApp } from "../test/render";

function point(overrides: Partial<ReviewPoint>): ReviewPoint {
  return {
    id: 21,
    position: 0,
    description: "Conducts electricity",
    alternatives: [],
    max_marks: 1,
    decision_id: 101,
    proposed_marks: 1,
    evidence: "conduct electricity",
    confidence: 0.9,
    error_category: "correct",
    deducted: 0,
    final_marks: null,
    final_category: null,
    decided_at: null,
    model_name: "qwen3-vl:4b-instruct",
    model_version: "ee4b975b58c1",
    prompt_version: "marker-v2#6bf69283",
    ...overrides,
  };
}

function review(overrides: Partial<ScriptReview> = {}): ScriptReview {
  return {
    script: {
      id: 5,
      status: "ai_marked",
      manual_reason: null,
      student_code: "AAAAAA",
      student_name: "Ama Fon",
      reviewed_at: null,
      confirmed_at: null,
    },
    exam: {
      id: 7,
      title: "Mock exam 1",
      subject_code: "chemistry",
      show_scheme_to_students: false,
    },
    ready: true,
    locked: false,
    can_confirm: false,
    pages: [
      {
        id: 31,
        position: 0,
        is_cover: true,
        width: 1654,
        height: 2339,
        rotation: 0,
        rotation_teacher: null,
        rotation_auto: 0,
        auto_rotated: false,
        auto_rotation_confidence: null,
        rotated_after_transcription: false,
        retranscribe_pending: false,
        transcription: null,
        versions: [],
        edited_after_marking: false,
      },
      {
        id: 32,
        position: 1,
        is_cover: false,
        width: 1654,
        height: 2339,
        rotation: 180,
        rotation_teacher: null,
        rotation_auto: 180,
        auto_rotated: true,
        auto_rotation_confidence: 0.93,
        rotated_after_transcription: false,
        retranscribe_pending: false,
        transcription: {
          id: 41,
          text: "1(a) Metals conduct electricity.\n1(b) Hydrogen",
          source: "model",
          model_name: "qwen3-vl:4b-instruct",
          model_version: "ee4b975b58c1",
          prompt_version: "reader-v2#abc",
          rotation: 180,
          created_at: "2026-10-15T08:00:00Z",
        },
        versions: [],
        edited_after_marking: false,
      },
    ],
    questions: [
      {
        id: 11,
        label: "1(a)",
        prompt_text: "State two properties of metals.",
        max_marks: 2,
        points: [
          point({}),
          point({
            id: 22,
            position: 1,
            description: "Malleable",
            decision_id: 102,
            proposed_marks: 0,
            evidence: "",
            confidence: 0.4,
            error_category: "omitted",
            deducted: 1,
          }),
        ],
        comment: "",
        proposed_total: 1,
        final_total: null,
        deductions: 1,
        marks_deducted: 1,
      },
    ],
    totals: {
      max_total: 2,
      proposed_total: 1,
      final_total: null,
      decided_points: 0,
      total_points: 2,
      deductions: 1,
      marks_deducted: 1,
    },
    navigation: { previous_id: null, next_id: 6, position: 1, count: 2 },
    marked_on_earlier_text: false,
    test_model: false,
    ai_run: 0,
    ...overrides,
  };
}

function setup(data: ScriptReview = review(), language: "en" | "fr" = "en") {
  const api = fakeApi();
  api.on("GET /api/auth/me", [200, me("teacher", language)]);
  api.on("GET /api/scripts/5/review", [200, data]);
  api.on("POST /api/scripts/5/review-heartbeat", [200, { session_open: true, active_seconds: 0 }]);
  return api;
}

function calls(api: ReturnType<typeof fakeApi>, method: string, path: string) {
  return api.calls.filter((c) => c.method === method && c.path === path);
}

describe("script review screen", () => {
  it("shows the page, transcription, proposals and AI deductions", async () => {
    setup();
    renderApp("/exams/7/review/5");

    expect(await screen.findByRole("heading", { name: /Ama Fon/ })).toBeInTheDocument();
    // The page is shown turned by its effective rotation, with the auto-rotation marked.
    expect(screen.getByAltText("Scanned page 2")).toBeInTheDocument();
    expect(screen.getByTestId("viewer-sheet")).toHaveStyle({
      transform: "translate(0px, 0px) scale(1) rotate(180deg)",
    });
    expect(screen.getByText(en.review.viewer.autoRotated)).toBeInTheDocument();
    // Owner, 2026-10-15: deductions are easy to spot.
    const badge = screen.getByLabelText("The AI gave 1 mark fewer than this point is worth");
    expect(badge).toHaveTextContent("−1");
    expect(badge.closest("li")).toHaveClass("point-deducted");
    expect(
      screen.getByText("AI deducted 1 mark(s) on 1 point", { selector: ".question-head *" }),
    ).toBeInTheDocument();
    // The focused point's evidence is highlighted in the transcription.
    expect(screen.getByText("conduct electricity", { selector: "mark" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.review.confirm })).toBeDisabled();
  });

  it("opens a review-time session on the local server", async () => {
    const api = setup();
    renderApp("/exams/7/review/5");
    await waitFor(() => {
      expect(calls(api, "POST", "/api/scripts/5/review-heartbeat")).toHaveLength(1);
    });
  });

  it("is driven from the keyboard", async () => {
    const api = setup();
    const after = review({ can_confirm: true });
    api.on("PUT /api/scripts/5/decisions/22", [200, after]);
    api.on("POST /api/scripts/5/decisions/21/accept", [200, after]);
    api.on("POST /api/scripts/5/accept-all", [200, { accepted: 1, review: after }]);
    api.on("POST /api/scripts/5/confirm", [200, review({ locked: true })]);
    api.on("POST /api/pages/32/rotation", [200, after]);
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByRole("heading", { name: /Ama Fon/ });

    await user.keyboard("a");
    await waitFor(() => {
      expect(calls(api, "POST", "/api/scripts/5/decisions/21/accept")).toHaveLength(1);
    });
    await user.keyboard("d"); // jump to the point with a deduction
    await waitFor(() => {
      expect(document.querySelector("[aria-current='true']")).toHaveAttribute(
        "data-point-id",
        "22",
      );
    });
    await user.keyboard("1");
    await waitFor(() => {
      expect(calls(api, "PUT", "/api/scripts/5/decisions/22").at(-1)?.body).toEqual({ marks: 1 });
    });
    await user.keyboard("c");
    await waitFor(() => {
      expect(calls(api, "PUT", "/api/scripts/5/decisions/22").at(-1)?.body).toEqual({
        category: "omitted",
      });
    });
    await user.keyboard("{Shift>}A{/Shift}");
    await waitFor(() => {
      expect(calls(api, "POST", "/api/scripts/5/accept-all")).toHaveLength(1);
    });
    await user.keyboard("r");
    await waitFor(() => {
      expect(calls(api, "POST", "/api/pages/32/rotation").at(-1)?.body).toEqual({ rotation: 270 });
    });
    await user.keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() => {
      expect(calls(api, "POST", "/api/scripts/5/confirm")).toHaveLength(1);
    });
    expect(await screen.findByText(en.review.confirmed)).toBeInTheDocument();
  });

  it("never drops keys pressed while an earlier change is still saving", async () => {
    // Found by the browser test: quick keys used to be ignored while a save was in flight.
    const api = setup();
    const after = review({ can_confirm: true });
    api.on("POST /api/scripts/5/decisions/21/accept", [200, after]);
    api.on("POST /api/scripts/5/accept-all", [200, { accepted: 1, review: after }]);
    api.on("POST /api/scripts/5/confirm", [200, review({ locked: true })]);
    const user = userEvent.setup({ delay: null });
    renderApp("/exams/7/review/5");
    await screen.findByRole("heading", { name: /Ama Fon/ });

    await user.keyboard("a{Shift>}A{/Shift}{Control>}{Enter}{/Control}");

    await waitFor(() => {
      expect(
        api.calls
          .filter((c) => c.method === "POST" && !c.path.endsWith("heartbeat"))
          .map((c) => c.path),
      ).toEqual([
        "/api/scripts/5/decisions/21/accept",
        "/api/scripts/5/accept-all",
        "/api/scripts/5/confirm",
      ]);
    });
  });

  it("refuses marks above the point's maximum without asking the server", async () => {
    const api = setup();
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByRole("heading", { name: /Ama Fon/ });

    await user.keyboard("2");

    expect(await screen.findByText("This point is worth at most 1.")).toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("ignores shortcuts while typing a comment, and saves it on leaving the box", async () => {
    const api = setup();
    api.on("PUT /api/scripts/5/questions/11/comment", [200, review()]);
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByRole("heading", { name: /Ama Fon/ });

    await user.keyboard("m"); // focus the comment of the current question
    const box = screen.getByRole("textbox", { name: new RegExp(en.review.comment) });
    expect(box).toHaveFocus();
    await user.keyboard("a1 good");
    expect(api.calls.some((c) => c.path.includes("/decisions/"))).toBe(false);
    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(calls(api, "PUT", "/api/scripts/5/questions/11/comment").at(-1)?.body).toEqual({
        text: "a1 good",
      });
    });
    expect(box).toHaveAttribute("maxlength", "300");
  });

  it("edits the transcription as a new version", async () => {
    const api = setup();
    api.on("POST /api/pages/32/transcription", [200, review()]);
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByRole("heading", { name: /Ama Fon/ });

    await user.keyboard("t");
    const editor = screen.getByRole("textbox", { name: en.review.transcription });
    expect(editor).toHaveFocus();
    await user.clear(editor);
    await user.type(editor, "1(a) corrected");
    await user.keyboard("{Control>}{Enter}{/Control}");

    await waitFor(() => {
      expect(calls(api, "POST", "/api/pages/32/transcription").at(-1)?.body).toEqual({
        text: "1(a) corrected",
      });
    });
    // Ctrl+Enter inside the editor saved the text; it did not confirm the script.
    expect(calls(api, "POST", "/api/scripts/5/confirm")).toHaveLength(0);
  });

  it("undoes an automatic rotation", async () => {
    const api = setup();
    api.on("POST /api/pages/32/undo-auto-rotation", [200, review()]);
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");

    await user.click(await screen.findByRole("button", { name: en.review.viewer.undoAuto }));

    await waitFor(() => {
      expect(calls(api, "POST", "/api/pages/32/undo-auto-rotation")).toHaveLength(1);
    });
  });

  it("locks a confirmed script until it is reopened", async () => {
    const api = setup(
      review({ locked: true, script: { ...review().script, status: "confirmed" } }),
    );
    api.on("POST /api/scripts/5/reopen", [200, review()]);
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByText(en.review.lockedNotice, { selector: "p" });

    await user.keyboard("1");
    expect(api.calls.some((c) => c.method === "PUT")).toBe(false);
    for (const button of screen.getAllByRole("button", { pressed: false })) {
      expect(button).toBeDisabled();
    }
    // No review time is recorded while a confirmed script is only being looked at.
    expect(calls(api, "POST", "/api/scripts/5/review-heartbeat")).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: en.review.reopen }));
    await waitFor(() => {
      expect(calls(api, "POST", "/api/scripts/5/reopen")).toHaveLength(1);
    });
  });

  it("lists the shortcuts on ?", async () => {
    setup();
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByRole("heading", { name: /Ama Fon/ });

    await user.keyboard("?");

    const dialog = screen.getByRole("dialog", { name: en.review.shortcuts });
    expect(within(dialog).getByText(en.review.keys.deduction)).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("is translated into French", async () => {
    setup(review(), "fr");
    renderApp("/exams/7/review/5");

    expect(await screen.findByRole("button", { name: fr.review.confirm })).toBeInTheDocument();
    expect(screen.getByText(fr.review.viewer.autoRotated)).toBeInTheDocument();
    expect(
      screen.getByLabelText("L'IA a donné 1 point de moins que la valeur de ce critère"),
    ).toBeInTheDocument();
  });
});

function queue(overrides: Partial<Queue> = {}): Queue {
  const base = {
    script_id: 5,
    student_code: "AAAAAA",
    student_name: "Ama Fon",
    status: "ai_marked" as const,
    manual_reason: null,
    reviewable: true,
    page_count: 3,
    page_count_flag: null,
    auto_rotated_pages: 0,
    min_confidence: 0.9,
    uncertain_points: 0,
    deductions: 0,
    marks_deducted: 0,
    decided_points: 0,
    total_points: 3,
    proposed_total: 3,
    final_total: null,
    max_total: 3,
    review_seconds: null,
    active_seconds: null,
    test_model: false,
  };
  return {
    exam_id: 7,
    exam_title: "Mock exam 1",
    exam_status: "reviewing",
    items: [
      {
        ...base,
        manual_reason: "ai.marker_invalid_output",
        deductions: 2,
        marks_deducted: 2,
        auto_rotated_pages: 1,
      },
      {
        ...base,
        script_id: 6,
        student_code: "BBBBBB",
        student_name: null,
        status: "confirmed",
        decided_points: 3,
        final_total: 2,
        review_seconds: 754,
        active_seconds: 300,
      },
      { ...base, script_id: 8, student_code: "CCCCCC", status: "waiting", reviewable: false },
    ],
    typical_page_count: 3,
    confirmed_count: 1,
    timed_count: 1,
    average_review_seconds: 754,
    average_active_seconds: 300,
    test_model_count: 0,
    ...overrides,
  };
}

describe("marking queue screen", () => {
  it("lists scripts with what to check and the class's average review time", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me()]);
    quietQueueExtras(api);
    api.on("GET /api/exams/7/queue", [200, queue()]);
    api.on("GET /api/exams/7/ai-status", [
      200,
      {
        scripts: { waiting: 1, transcribed: 0, ai_marked: 1, in_review: 0, confirmed: 1 },
        flagged: [],
        jobs_queued: 0,
        jobs_running: 0,
        jobs_failed: 0,
        system: {
          worker_online: true,
          ai_backend: "mock",
          model_server_reachable: true,
          reader_model: "mock",
          reader_model_installed: true,
          marker_model: "mock",
          marker_model_installed: true,
        },
      },
    ]);
    renderApp("/exams/7/queue");

    const rows = await screen.findAllByRole("row");
    expect(rows).toHaveLength(4);
    const first = at(rows, 1);
    expect(
      within(first).getByText(en.ai.manualReason.ai.marker_invalid_output),
    ).toBeInTheDocument();
    expect(within(first).getByText("AI deducted 2 on 2 points")).toBeInTheDocument();
    expect(within(first).getByText("1 page turned automatically")).toBeInTheDocument();
    expect(within(first).getByRole("link", { name: en.queue.review })).toHaveAttribute(
      "href",
      "/exams/7/review/5",
    );
    expect(within(at(rows, 2)).getByRole("link", { name: en.queue.open })).toBeInTheDocument();
    expect(within(at(rows, 3)).getByText(en.queue.waitingForAi)).toBeInTheDocument();
    expect(screen.getByText(/Average review time \(1 confirmed script\)/)).toHaveTextContent(
      "12 min 34 s",
    );
    expect(screen.getByText(en.queue.localOnly)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: en.ai.start })).toBeInTheDocument();
  });
});

describe("test-model output and re-running AI marking (owner, 2026-10-15)", () => {
  it("labels a script read and marked by the test model, and names every model", async () => {
    const testPoint = point({ model_name: "mock-marker", model_version: "mock-1" });
    setup(
      review({
        test_model: true,
        questions: [{ ...at(review().questions, 0), points: [testPoint] }],
      }),
    );
    renderApp("/exams/7/review/5");

    expect(await screen.findByRole("alert")).toHaveTextContent(en.testModel.short);
    expect(
      screen.getByText(/Model: mock-marker · mock-1 · marker-v2#6bf69283/),
    ).toBeInTheDocument();
    // The transcription names its model and version too.
    expect(
      screen.getByText(/Model: qwen3-vl:4b-instruct · ee4b975b58c1 · reader-v2#abc/),
    ).toBeInTheDocument();
  });

  it("names the real model on proposals without a test label", async () => {
    setup();
    renderApp("/exams/7/review/5");
    expect(
      (await screen.findAllByText(/Model: qwen3-vl:4b-instruct · ee4b975b58c1 · marker-v2/)).length,
    ).toBe(2);
    expect(screen.queryByText(en.testModel.short)).not.toBeInTheDocument();
  });

  it("re-runs AI marking for the script after asking once more", async () => {
    const api = setup();
    api.on("POST /api/scripts/5/rerun-ai", [
      202,
      review({ ready: false, script: { ...review().script, status: "waiting" } }),
    ]);
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");

    await user.click(await screen.findByRole("button", { name: en.rerun.script }));
    expect(screen.getByText(en.rerun.scriptQuestion)).toBeInTheDocument();
    expect(api.calls.some((c) => c.path === "/api/scripts/5/rerun-ai")).toBe(false);
    await user.click(screen.getByRole("button", { name: en.common.yes }));

    await waitFor(() => {
      expect(api.calls.filter((c) => c.path === "/api/scripts/5/rerun-ai")).toHaveLength(1);
    });
    expect(await screen.findByText(en.rerun.scriptStarted)).toBeInTheDocument();
    expect(screen.getByText(en.review.notReady)).toBeInTheDocument();
  });

  it("offers no re-run on a confirmed script", async () => {
    setup(review({ locked: true, script: { ...review().script, status: "confirmed" } }));
    renderApp("/exams/7/review/5");
    await screen.findByRole("button", { name: en.review.reopen });
    expect(screen.queryByRole("button", { name: en.rerun.script })).not.toBeInTheDocument();
  });

  it("labels test-model scripts in the queue and re-runs the exam's unconfirmed scripts", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me()]);
    const data = queue({ test_model_count: 1 });
    data.items = data.items.map((item, index) =>
      index === 0 ? { ...item, test_model: true } : item,
    );
    quietQueueExtras(api);
    api.on("GET /api/exams/7/queue", [200, data]);
    api.on("GET /api/exams/7/ai-status", [
      200,
      {
        scripts: {},
        flagged: [],
        jobs_queued: 0,
        jobs_running: 0,
        jobs_failed: 0,
        system: {
          worker_online: true,
          ai_backend: "ollama",
          model_server_reachable: true,
          reader_model: "m",
          reader_model_installed: true,
          marker_model: "m",
          marker_model_installed: true,
        },
      },
    ]);
    api.on("POST /api/exams/7/rerun-ai", [202, { scripts_queued: 1 }]);
    const user = userEvent.setup();
    renderApp("/exams/7/queue");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /1 script was read or marked by the test model/,
    );
    const rows = screen.getAllByRole("row");
    expect(within(at(rows, 1)).getByText(en.testModel.short)).toBeInTheDocument();
    expect(within(at(rows, 2)).queryByText(en.testModel.short)).not.toBeInTheDocument();

    // One unconfirmed script the AI has finished with: the confirmed and waiting ones are not counted.
    await user.click(
      screen.getByRole("button", { name: "Re-run AI marking (1 unconfirmed script)" }),
    );
    await user.click(screen.getByRole("button", { name: en.common.yes }));
    expect(await screen.findByText("AI marking started again for 1 script.")).toBeInTheDocument();
  });
});

describe("the marking desk (design pass)", () => {
  function twoQuestions(overrides: Partial<ScriptReview> = {}): ScriptReview {
    const base = review();
    const first = at(base.questions, 0);
    return review({
      questions: [
        first,
        {
          ...first,
          id: 12,
          label: "1(b)",
          prompt_text: "Name the gas.",
          max_marks: 1,
          points: [point({ id: 23, description: "Hydrogen", evidence: "Hydrogen", deducted: 0 })],
          deductions: 0,
          marks_deducted: 0,
        },
      ],
      ...overrides,
    });
  }

  it("shows one question at a time and moves between questions with the arrow keys", async () => {
    setup(twoQuestions());
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByRole("heading", { name: /Ama Fon/ });

    expect(screen.getByRole("heading", { name: /Question 1\(a\)/ })).toBeInTheDocument();
    expect(screen.queryByText("Hydrogen", { selector: ".point-description" })).toBeNull();
    await user.keyboard("{ArrowRight}");
    expect(await screen.findByRole("heading", { name: /Question 1\(b\)/ })).toBeInTheDocument();
    expect(screen.getByText("Hydrogen", { selector: ".point-description" })).toBeInTheDocument();
    // The evidence line numbers are given beside the AI's proposal.
    expect(screen.getByText("Line 2, page 2")).toBeInTheDocument();
    await user.keyboard("{ArrowLeft}");
    expect(await screen.findByRole("heading", { name: /Question 1\(a\)/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Question 1\(b\): – of 1/ }));
    expect(screen.getByRole("heading", { name: /Question 1\(b\)/ })).toBeInTheDocument();
  });

  it("hides and shows the evidence with E", async () => {
    setup();
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByText("conduct electricity", { selector: "mark" });

    await user.keyboard("e");
    expect(screen.queryByText("conduct electricity", { selector: "mark" })).toBeNull();
    expect(screen.getByRole("button", { name: en.review.viewer.evidence })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await user.keyboard("e");
    expect(screen.getByText("conduct electricity", { selector: "mark" })).toBeInTheDocument();
  });

  it("confirms with Enter and settles the total in the confirmed state", async () => {
    const api = setup(review({ can_confirm: true }));
    api.on("POST /api/scripts/5/confirm", [
      200,
      review({
        locked: true,
        script: { ...review().script, status: "confirmed" },
        totals: { ...review().totals, final_total: 2 },
      }),
    ]);
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByRole("heading", { name: /Ama Fon/ });

    await user.keyboard("{Enter}");

    expect(await screen.findByText(en.review.confirmed)).toBeInTheDocument();
    const total = screen.getByText("Total: 2 / 2").closest("p");
    expect(total).toHaveClass("desk-score-confirmed");
    expect(total).toHaveClass("desk-score-stamp");
  });

  it("lets Enter press a focused button instead of confirming", async () => {
    const api = setup(review({ can_confirm: true }));
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByRole("heading", { name: /Ama Fon/ });

    screen.getByRole("button", { name: en.review.shortcuts }).focus();
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("dialog", { name: en.review.shortcuts })).toBeInTheDocument();
    expect(calls(api, "POST", "/api/scripts/5/confirm")).toHaveLength(0);
  });
});

describe("red pen on screen (owner, 2026-10-15)", () => {
  function redPen(): RedPen {
    return {
      total: "1/2",
      pages: [
        {
          page_id: 32,
          placed: true,
          marks: [
            {
              kind: "tick",
              x: 0.5,
              y: 0.2,
              size: 0.04,
              text: "",
              width: 0,
              question_id: 11,
              point_id: 21,
              pending: false,
            },
            {
              kind: "cross",
              x: 0.56,
              y: 0.2,
              size: 0.04,
              text: "",
              width: 0,
              question_id: 11,
              point_id: 22,
              pending: true,
            },
            {
              kind: "score",
              x: 0.1,
              y: 0.2,
              size: 0.03,
              text: "1/2",
              width: 0,
              question_id: 11,
              point_id: null,
              pending: false,
            },
            {
              kind: "comment",
              x: 0.15,
              y: 0.25,
              size: 0.025,
              text: "Name a second property.",
              width: 0.6,
              question_id: 11,
              point_id: null,
              pending: false,
            },
          ],
          unplaced_comments: [],
        },
      ],
    };
  }

  it("draws the red pen over the page and red signs beside each point", async () => {
    const api = setup();
    api.on("GET /api/scripts/5/red-pen", [200, redPen()]);
    renderApp("/exams/7/review/5");

    const overlay = await screen.findByTestId("red-pen");
    expect(overlay.querySelectorAll("[data-kind='tick']")).toHaveLength(1);
    expect(overlay.querySelectorAll("[data-kind='cross']")).toHaveLength(1);
    expect(within(overlay).getByText("1/2")).toBeInTheDocument();
    expect(within(overlay).getByText("Name a second property.")).toBeInTheDocument();
    // Signs beside the points: full marks and (proposed) no marks.
    expect(screen.getAllByLabelText(en.redPen.signFull).length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText(en.redPen.signNone).length).toBeGreaterThan(0);
  });

  it("can be switched off", async () => {
    const api = setup();
    api.on("GET /api/scripts/5/red-pen", [200, redPen()]);
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");
    await screen.findByTestId("red-pen");

    await user.click(screen.getByRole("checkbox", { name: en.redPen.show }));

    expect(screen.queryByTestId("red-pen")).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: en.redPen.show }));
    expect(await screen.findByTestId("red-pen")).toBeInTheDocument();
  });

  it("offers no mark scheme suggestion while the exam keeps the scheme from students", async () => {
    const api = setup();
    api.on("GET /api/scripts/5/red-pen", [200, redPen()]);
    renderApp("/exams/7/review/5");

    await screen.findByTestId("red-pen");
    expect(screen.queryByRole("button", { name: en.redPen.suggest })).not.toBeInTheDocument();
  });

  it("suggests a comment from the mark scheme for the points not earned", async () => {
    const base = review();
    const api = setup({ ...base, exam: { ...base.exam, show_scheme_to_students: true } });
    api.on("GET /api/scripts/5/red-pen", [200, redPen()]);
    api.on("PUT /api/scripts/5/questions/11/comment", [200, review()]);
    const user = userEvent.setup();
    renderApp("/exams/7/review/5");

    await user.click(await screen.findByRole("button", { name: en.redPen.suggest }));

    await waitFor(() => {
      const call = api.calls.find((c) => c.path === "/api/scripts/5/questions/11/comment");
      expect(call?.body).toEqual({ text: "Missing: Malleable" });
    });
  });
});
