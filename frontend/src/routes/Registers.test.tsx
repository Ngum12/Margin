import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { fakeApi, me } from "../test/fakeApi";
import { renderApp } from "../test/render";
import en from "../i18n/locales/en.json";

describe("class register preview", () => {
  it("lets the teacher correct an imported name before confirmation", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me()]);
    api.on("GET /api/classes", [
      200,
      [
        {
          id: 3,
          name: "Form 4A",
          academic_year: "2026/2027",
          teacher_id: 1,
          teacher_name: "Alice",
          student_count: 0,
        },
      ],
    ]);
    api.on("GET /api/classes/3/students", [200, []]);
    api.on("GET /api/classes/3/imports", [
      200,
      [
        {
          id: 8,
          status: "ready",
          error: null,
          model_name: null,
          rows: [{ name: "Ame Fon", code: "" }],
        },
      ],
    ]);
    api.on("POST /api/roster-imports/8/confirm", [200, []]);
    renderApp("/registers");
    const user = userEvent.setup();
    await screen.findByRole("option", { name: /Form 4A/ });
    await user.selectOptions(screen.getByRole("combobox", { name: en.portal.class }), "3");
    const name = await screen.findByRole("textbox", { name: en.students.name });
    await user.clear(name);
    await user.type(name, "Ama Fon");
    expect(api.calls.some((c) => c.path.endsWith("/confirm"))).toBe(false);
    await user.click(screen.getByRole("button", { name: en.register.confirm }));
    await waitFor(() => {
      expect(api.calls.find((c) => c.path.endsWith("/confirm"))?.body).toEqual({
        rows: [{ name: "Ama Fon", code: "" }],
      });
    });
  });
});
