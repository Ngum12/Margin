import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ExportJob, Results, TrainingExport } from "../api/types";
import en from "../i18n/locales/en.json";
import fr from "../i18n/locales/fr.json";
import { at } from "../test/at";
import { fakeApi, me, SUBJECTS } from "../test/fakeApi";
import { renderApp } from "../test/render";

function results(overrides: Partial<Results> = {}): Results {
  return {
    exam_id: 7,
    exam_title: "Mock exam 1",
    exam_status: "reviewing",
    questions: [
      { id: 11, label: "1(a)", max_marks: 2, average: 1.5 },
      { id: 12, label: "1(b)", max_marks: 1, average: 1 },
    ],
    rows: [
      {
        script_id: 5,
        student_code: "AAAAAA",
        student_name: "Ama Fon",
        status: "confirmed",
        confirmed: true,
        marks: [1, 1],
        total: 2,
        percentage: 66.7,
      },
      {
        script_id: 6,
        student_code: "BBBBBB",
        student_name: null,
        status: "in_review",
        confirmed: false,
        marks: [null, null],
        total: null,
        percentage: null,
      },
    ],
    max_total: 3,
    average_total: 2,
    confirmed_count: 1,
    script_count: 2,
    timed_count: 1,
    average_review_seconds: 125,
    average_active_seconds: 90,
    class_pdfs: [],
    ...overrides,
  };
}

function job(overrides: Partial<ExportJob> = {}): ExportJob {
  return {
    id: 3,
    kind: "class_pdf",
    status: "pending",
    filename: "mock-exam-1-marked-scripts.pdf",
    size_bytes: null,
    error_code: null,
    created_at: "2026-10-15T10:00:00Z",
    finished_at: null,
    ...overrides,
  };
}

describe("results screen", () => {
  it("shows confirmed marks, hides unconfirmed ones, and offers the exports", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me()]);
    api.on("GET /api/exams/7/results", [200, results()]);
    renderApp("/exams/7/results");

    const rows = await screen.findAllByRole("row");
    const confirmed = at(rows, 1);
    expect(within(confirmed).getByText("AAAAAA")).toBeInTheDocument();
    expect(within(confirmed).getByText("66.7")).toBeInTheDocument();
    expect(within(confirmed).getByRole("link", { name: "Marked PDF for AAAAAA" })).toHaveAttribute(
      "href",
      "/api/scripts/5/marked.pdf",
    );
    const pending = at(rows, 2);
    expect(within(pending).queryByRole("link")).not.toBeInTheDocument();
    expect(within(pending).getByText(/In review/)).toBeInTheDocument();
    expect(
      screen.getByText(
        "1 script is not confirmed yet: it is shown without marks and is not included in any export.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en.results.downloadCsv })).toHaveAttribute(
      "href",
      "/api/exams/7/results.csv",
    );
    expect(screen.getByText(/Average review time \(1 confirmed script\)/)).toHaveTextContent(
      "2 min 5 s",
    );
  });

  it("prepares the class PDF in the background and offers it when ready", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me()]);
    api.on("GET /api/exams/7/results", [200, results()]);
    api.on("POST /api/exams/7/exports/class-pdf", [202, job()]);
    api.on("GET /api/exports/3", [200, job({ status: "done", size_bytes: 2_500_000 })]);
    const user = userEvent.setup();
    renderApp("/exams/7/results");

    await user.click(await screen.findByRole("button", { name: en.results.classPdf }));

    expect(await screen.findByText(en.exports.preparing)).toBeInTheDocument();
    const link = await screen.findByRole(
      "link",
      { name: "Download mock-exam-1-marked-scripts.pdf" },
      { timeout: 6000 },
    );
    expect(link).toHaveAttribute("href", "/api/exports/3/file");
    expect(screen.getByText(/2\.4 MB/)).toBeInTheDocument();
  });

  it("offers nothing to export before a script is confirmed, in French", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me("teacher", "fr")]);
    api.on("GET /api/exams/7/results", [
      200,
      results({ confirmed_count: 0, rows: [], average_total: null, timed_count: 0 }),
    ]);
    renderApp("/exams/7/results");

    expect(await screen.findByText(fr.results.nothingToExport)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: fr.results.downloadCsv })).not.toBeInTheDocument();
  });
});

function training(): TrainingExport {
  return {
    exams: [
      { exam_id: 7, title: "Mock exam 1", subject_code: "chemistry", confirmed: 3, consented: 2 },
      { exam_id: 8, title: "Mock exam 2", subject_code: "chemistry", confirmed: 1, consented: 0 },
    ],
    exports: [],
  };
}

describe("admin models and training data", () => {
  it("shows the model configuration and exports consented scripts only", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me("admin")]);
    api.on("GET /api/subjects", [200, SUBJECTS]);
    api.on("GET /api/admin/training-export", [200, training()]);
    api.on("GET /api/admin/model-config", [
      200,
      {
        ai_backend: "ollama",
        model_host: "127.0.0.1:11434",
        reader_model: "qwen3-vl:4b-instruct",
        marker_model: "qwen3-vl:4b-instruct",
        marker_evidence: "quote",
        model_timeout_seconds: 300,
        model_output_retries: 2,
        orientation_check: "off",
      },
    ]);
    api.on("GET /api/system/status", [
      200,
      {
        worker_online: true,
        ai_backend: "ollama",
        model_server_reachable: true,
        reader_model: "qwen3-vl:4b-instruct",
        reader_model_installed: true,
        marker_model: "qwen3-vl:4b-instruct",
        marker_model_installed: true,
      },
    ]);
    api.on("POST /api/admin/training-export", [202, job({ id: 9, kind: "dataset" })]);
    api.on("GET /api/exports/9", [200, job({ id: 9, kind: "dataset", status: "pending" })]);
    const user = userEvent.setup();
    renderApp("/admin/training-data");

    expect(await screen.findByText("300 seconds")).toBeInTheDocument();
    expect(screen.getByText("127.0.0.1:11434")).toBeInTheDocument();
    // An exam with no consenting student cannot be chosen.
    expect(screen.getByRole("checkbox", { name: "Include Mock exam 2" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Export 2 scripts" }));

    await waitFor(() => {
      const call = api.calls.find(
        (c) => c.path === "/api/admin/training-export" && c.method === "POST",
      );
      expect(call?.body).toEqual({ exam_ids: [7] });
    });
    expect(await screen.findByText(en.exports.preparing)).toBeInTheDocument();
  });
});
