import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeApi } from "../test/fakeApi";
import { renderApp } from "../test/render";
import en from "../i18n/locales/en.json";

describe("student portal", () => {
  it("requires the initial PIN change before loading released work", async () => {
    const api = fakeApi();
    const student = {
      code: "ABCDEF",
      name: "Student A",
      must_change_pin: true,
      csrf_token: "student-csrf",
    };
    api.on("GET /api/student/me", [200, student]);
    api.on("PUT /api/student/pin", [200, { ...student, must_change_pin: false }]);
    api.on("GET /api/student/exams", [200, []]);
    renderApp("/student");
    expect(await screen.findByRole("heading", { name: en.portal.changePin })).toBeInTheDocument();
    expect(api.calls.some((c) => c.path === "/api/student/exams")).toBe(false);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(en.portal.oldPin), "12345678");
    await user.type(screen.getByLabelText(en.portal.newPin), "87654321");
    await user.click(screen.getByRole("button", { name: en.common.save }));
    expect(await screen.findByText(en.portal.noExams)).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PUT")?.headers["X-CSRF-Token"]).toBe("student-csrf");
    expect(screen.queryByRole("navigation", { name: en.nav.label })).not.toBeInTheDocument();
  });

  it("shows released work without exposing a hidden scheme and clears it on sign out", async () => {
    const api = fakeApi();
    api.on("GET /api/student/me", [
      200,
      { code: "ABCDEF", name: null, must_change_pin: false, csrf_token: "student-csrf" },
    ]);
    api.on("GET /api/student/exams", [
      200,
      [
        {
          id: 1,
          exam_id: 3,
          title: "Chemistry June",
          subject: "chemistry",
          date: "2026-06-01",
          total: 1,
          maximum: 2,
          visibility: "notes",
          released_at: "2026-06-02",
          remark_days: 7,
          remark_max: 3,
          escalation: false,
          pages: [],
          remarks: [],
          questions: [
            {
              id: 8,
              label: "Q1",
              prompt: "Explain your method",
              marks: 1,
              maximum: 2,
              comment: "Check the arithmetic",
              feedback: [],
              scheme: [],
            },
          ],
        },
      ],
    ]);
    api.on("GET /api/student/scripts/1/marks", [200, { pages: [] }]);
    api.on("POST /api/student/logout", [204]);
    api.on("GET /api/student/schools", [200, [{ id: 1, name: "School A" }]]);
    renderApp("/student");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Chemistry June/ }));
    expect(await screen.findByText("Check the arithmetic")).toBeInTheDocument();
    expect(screen.queryByText(en.portal.scheme)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: en.portal.signout }));
    await waitFor(() => {
      expect(screen.queryByText("Check the arithmetic")).not.toBeInTheDocument();
    });
    expect(await screen.findByRole("heading", { name: en.portal.signin })).toBeInTheDocument();
  });
});
