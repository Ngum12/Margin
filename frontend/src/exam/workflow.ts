// Where an exam is in its workflow, for the exam tabs. Pure functions, unit-tested.

import type { ExamStatus } from "../api/types";

export type StepState = "done" | "action" | "progress" | "later";

export interface ExamProgress {
  status: ExamStatus;
  scripts: { waiting: number; ai_marked: number; confirmed: number };
  // Null when not known (the cover sheet list could not be loaded).
  sheetsReady: boolean | null;
}

export interface WorkflowSteps {
  setup: StepState;
  sheets: StepState;
  scans: StepState;
  queue: StepState;
  results: StepState;
}

export function workflowSteps({ status, scripts, sheetsReady }: ExamProgress): WorkflowSteps {
  const total = scripts.waiting + scripts.ai_marked + scripts.confirmed;
  if (status === "draft") {
    return { setup: "action", sheets: "later", scans: "later", queue: "later", results: "later" };
  }
  const allConfirmed = total > 0 && scripts.confirmed === total;
  return {
    setup: "done",
    sheets: sheetsReady === false && total === 0 ? "action" : "done",
    scans: total > 0 ? "done" : "action",
    queue:
      total === 0 ? "later" : allConfirmed ? "done" : scripts.ai_marked > 0 ? "action" : "progress",
    results: allConfirmed ? "done" : scripts.confirmed > 0 ? "progress" : "later",
  };
}
