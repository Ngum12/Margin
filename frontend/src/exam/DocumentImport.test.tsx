import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { fakeApi } from "../test/fakeApi";
import { DocumentImport } from "./DocumentImport";

it("loads a proposed scheme only after the teacher chooses it", async () => {
  const api = fakeApi();
  const onLoad = vi.fn();
  const proposal = {
    questions: [
      {
        label: "1",
        prompt_text: "",
        max_marks: 1,
        points: [
          { description: "Hydrogen", marks: 1, alternatives: [], rules: { teacher_only: true } },
        ],
      },
    ],
  };
  api.on("GET /api/exams/7/scheme-documents", [
    200,
    [
      {
        id: 1,
        kind: "scheme",
        suffix: ".pdf",
        status: "ready",
        text: "1 Hydrogen",
        proposal,
        error: null,
      },
    ],
  ]);
  api.on("GET /api/scheme-library", [200, []]);
  render(<DocumentImport examId={7} editable onLoad={onLoad} />);
  const button = await screen.findByRole("button", { name: "Use this draft in the editor" });
  expect(onLoad).not.toHaveBeenCalled();
  await userEvent.setup().click(button);
  await waitFor(() => {
    expect(onLoad).toHaveBeenCalledWith(proposal);
  });
  expect(api.calls.filter((call) => call.method !== "GET")).toHaveLength(0);
});
