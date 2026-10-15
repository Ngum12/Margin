import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { MarkSchemeInput } from "../api/types";
import en from "../i18n/locales/en.json";
import fr from "../i18n/locales/fr.json";
import { examDetail, fakeApi, me, SUBJECTS } from "../test/fakeApi";
import { renderApp } from "../test/render";
import { at } from "../test/at";

function setup(language: "en" | "fr" = "en") {
  const api = fakeApi();
  api.on("GET /api/auth/me", [200, me("teacher", language)]);
  api.on("GET /api/subjects", [200, SUBJECTS]);
  api.on("GET /api/exams/7", [200, examDetail()]);
  return api;
}

describe("exam setup", () => {
  it("turns on showing the mark scheme to students", async () => {
    const api = setup();
    api.on("PUT /api/exams/7/settings", [200, examDetail({ show_scheme_to_students: true })]);
    const user = userEvent.setup();
    renderApp("/exams/7");

    const box = await screen.findByRole("checkbox", { name: en.exam.showScheme });
    expect(box).not.toBeChecked();
    await user.click(box);

    await waitFor(() => {
      expect(box).toBeChecked();
    });
    const call = api.calls.find((c) => c.path === "/api/exams/7/settings");
    expect(call?.body).toEqual({ show_scheme_to_students: true });
  });

  it("shows the existing mark scheme and exam total", async () => {
    setup();
    renderApp("/exams/7");

    expect(await screen.findByDisplayValue("1(a)")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Conducts electricity")).toBeInTheDocument();
    expect(screen.getByText("Exam total: 2 marks")).toBeInTheDocument();
  });

  it("enables saving only after a change and sends whole marks", async () => {
    const api = setup();
    api.on("PUT /api/exams/7/mark-scheme", (body) => {
      const scheme = body as MarkSchemeInput;
      return [
        200,
        examDetail({
          questions: scheme.questions.map((q, i) => ({
            ...q,
            id: i,
            points: q.points.map((p, j) => ({ ...p, id: j })),
          })),
        }),
      ];
    });
    const user = userEvent.setup();
    renderApp("/exams/7");

    const save = await screen.findByRole("button", { name: en.editor.save });
    expect(save).toBeDisabled();

    await user.click(screen.getByRole("button", { name: en.editor.addQuestion }));
    const labels = screen.getAllByLabelText(en.editor.label);
    await user.clear(at(labels, 1));
    await user.type(at(labels, 1), "2");
    const descriptions = screen.getAllByLabelText(en.editor.pointDescription);
    await user.type(at(descriptions, 2), "Hydrogen");
    await user.click(save);

    await waitFor(() => {
      expect(api.calls.some((c) => c.method === "PUT")).toBe(true);
    });
    const body = api.calls.find((c) => c.method === "PUT")?.body as MarkSchemeInput;
    expect(body.questions.map((q) => q.label)).toEqual(["1(a)", "2"]);
    expect(body.questions[1]?.points[0]).toEqual({
      description: "Hydrogen",
      marks: 1,
      alternatives: [],
    });
    expect(await screen.findByText(en.editor.saved)).toBeInTheDocument();
  });

  it("blocks saving and explains a duplicate label", async () => {
    setup();
    const user = userEvent.setup();
    renderApp("/exams/7");

    await user.click(await screen.findByRole("button", { name: en.editor.addQuestion }));
    const labels = screen.getAllByLabelText(en.editor.label);
    await user.clear(at(labels, 1));
    await user.type(at(labels, 1), "1(A)");

    expect(screen.getByRole("button", { name: en.editor.save })).toBeDisabled();
    expect(screen.getAllByText(/is already used by question 1/).length).toBeGreaterThan(0);
  });

  it("does not allow marking ready with unsaved changes", async () => {
    setup();
    const user = userEvent.setup();
    renderApp("/exams/7");

    const ready = await screen.findByRole("button", { name: en.editor.markReady });
    expect(ready).toBeEnabled();

    await user.type(screen.getByDisplayValue("Malleable"), " metal");

    expect(ready).toBeDisabled();
    expect(screen.getByText(en.editor.unsaved)).toBeInTheDocument();
  });

  it("shows validation problems in French", async () => {
    setup("fr");
    const user = userEvent.setup();
    renderApp("/exams/7");

    const maxMarks = await screen.findByLabelText(fr.editor.maxMarks);
    await user.clear(maxMarks);
    await user.type(maxMarks, "5");

    expect(
      screen.getAllByText(/les éléments totalisent 2, moins que le maximum de 5/).length,
    ).toBeGreaterThan(0);
  });

  it("shows a read-only scheme once the exam is ready", async () => {
    const api = setup();
    api.on("GET /api/exams/7", [200, examDetail({ status: "ready" })]);
    renderApp("/exams/7");

    expect(await screen.findByText(en.editor.lockedHelp)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en.editor.save })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.editor.backToDraft })).toBeInTheDocument();
  });

  it("previews a CSV import and loads it into the editor", async () => {
    const api = setup();
    api.on("POST /api/mark-scheme/import-preview", [
      200,
      {
        scheme: {
          questions: [
            {
              label: "Q9",
              prompt_text: "",
              max_marks: 4,
              points: [{ description: "Supply", marks: 4, alternatives: [] }],
            },
          ],
        },
        issues: [],
        validation: { blocking: [], readiness: [], notices: [], is_ready: true },
      },
    ]);
    const user = userEvent.setup();
    renderApp("/exams/7");

    await user.click(await screen.findByText(en.import.title));
    const file = new File(["question_label,...\n"], "scheme.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText(en.import.choose), file);
    await user.click(await screen.findByRole("button", { name: en.import.load }));

    expect(screen.getByDisplayValue("Q9")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("1(a)")).not.toBeInTheDocument();
    const call = api.calls.find((c) => c.path === "/api/mark-scheme/import-preview");
    expect(call?.headers["Content-Type"]).toBe("text/csv");
  });
});
