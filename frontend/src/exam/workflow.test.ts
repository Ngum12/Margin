import { describe, expect, it } from "vitest";

import { workflowSteps } from "./workflow";

const none = { waiting: 0, ai_marked: 0, confirmed: 0 };

describe("exam workflow tabs", () => {
  it("asks for the mark scheme first", () => {
    expect(workflowSteps({ status: "draft", scripts: none, sheetsReady: null })).toEqual({
      setup: "action",
      sheets: "later",
      scans: "later",
      queue: "later",
      results: "later",
    });
  });

  it("then cover sheets and scans", () => {
    const steps = workflowSteps({ status: "ready", scripts: none, sheetsReady: false });
    expect(steps.setup).toBe("done");
    expect(steps.sheets).toBe("action");
    expect(steps.scans).toBe("action");
    expect(workflowSteps({ status: "ready", scripts: none, sheetsReady: true }).sheets).toBe(
      "done",
    );
  });

  it("asks for review while the AI's scripts wait, and is done when all are confirmed", () => {
    const reviewing = workflowSteps({
      status: "reviewing",
      scripts: { waiting: 1, ai_marked: 2, confirmed: 1 },
      sheetsReady: true,
    });
    expect(reviewing).toMatchObject({ scans: "done", queue: "action", results: "progress" });
    const withAi = workflowSteps({
      status: "marking",
      scripts: { waiting: 3, ai_marked: 0, confirmed: 0 },
      sheetsReady: true,
    });
    expect(withAi).toMatchObject({ queue: "progress", results: "later" });
    const finished = workflowSteps({
      status: "completed",
      scripts: { waiting: 0, ai_marked: 0, confirmed: 4 },
      sheetsReady: true,
    });
    expect(finished).toMatchObject({ queue: "done", results: "done" });
  });
});
