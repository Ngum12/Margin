import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import en from "./i18n/locales/en.json";
import fr from "./i18n/locales/fr.json";
import { at } from "./test/at";
import { fakeApi, me } from "./test/fakeApi";
import { renderApp } from "./test/render";

const EXAMS = [
  {
    id: 7,
    class_id: 3,
    class_name: "Form 5A",
    subject_code: "chemistry",
    title: "Mock exam 1",
    exam_date: "2026-11-20",
    status: "ready",
    question_count: 2,
    total_marks: 3,
    scripts: { waiting: 0, ai_marked: 0, confirmed: 0 },
    updated_at: "2026-10-14T08:00:00Z",
  },
];

describe("sign in", () => {
  it("sends signed-out users to the sign-in page", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [401, { code: "auth.required" }]);

    renderApp("/");

    expect(await screen.findByRole("heading", { name: en.signIn.title })).toBeInTheDocument();
  });

  it("shows a plain-language error for a wrong password and clears it", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [401, { code: "auth.required" }]);
    api.on("POST /api/auth/login", [401, { code: "auth.invalid_credentials" }]);
    const user = userEvent.setup();
    renderApp("/signin");

    await user.type(await screen.findByLabelText(en.signIn.username), "alice");
    await user.type(screen.getByLabelText(en.signIn.password), "wrong");
    await user.click(screen.getByRole("button", { name: en.signIn.submit }));

    expect(await screen.findByRole("alert")).toHaveTextContent(en.errors.auth.invalid_credentials);
    expect(screen.getByLabelText(en.signIn.password)).toHaveValue("");
  });

  it("signs in and shows the teacher's exams with status and counts", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [401, { code: "auth.required" }]);
    api.on("POST /api/auth/login", [200, me()]);
    api.on("GET /api/exams", [200, EXAMS]);
    api.on("GET /api/subjects", [
      200,
      [{ code: "chemistry", name_en: "Chemistry", name_fr: "Chimie" }],
    ]);
    const user = userEvent.setup();
    renderApp("/signin");

    await user.type(await screen.findByLabelText(en.signIn.username), "alice");
    await user.type(screen.getByLabelText(en.signIn.password), "correct-horse");
    await user.click(screen.getByRole("button", { name: en.signIn.submit }));

    expect(await screen.findByRole("link", { name: "Mock exam 1" })).toBeInTheDocument();
    const row = screen.getByRole("row", { name: /Mock exam 1/ });
    expect(within(row).getByText(en.examStatus.ready)).toBeInTheDocument();
    expect(await within(row).findByText("Chemistry")).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === "/api/auth/login")?.body).toEqual({
      username: "alice",
      password: "correct-horse",
    });
  });

  it("explains when the server cannot be reached", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [503, null]);

    renderApp("/");

    expect(await screen.findByRole("alert")).toHaveTextContent(en.errors.network.unreachable);
  });
});

describe("what needs you today", () => {
  it("counts the work in order and links to it", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me()]);
    api.on("GET /api/subjects", [200, []]);
    const exam = at(EXAMS, 0);
    api.on("GET /api/exams", [
      200,
      [
        exam,
        {
          ...exam,
          id: 8,
          title: "Physics test",
          status: "reviewing",
          scripts: { waiting: 1, ai_marked: 3, confirmed: 2 },
        },
      ],
    ]);
    renderApp("/");

    const work = await screen.findByRole("list", { name: en.home.workLabel });
    const [scans, review, confirmed] = Array.from(work.children) as HTMLElement[];
    if (!scans || !review || !confirmed) throw new Error("three steps expected");
    expect(scans).toHaveTextContent(`1 ${en.home.needScans_one}`);
    expect(within(scans).getByRole("link", { name: /Mock exam 1/ })).toHaveAttribute(
      "href",
      "/exams/7/scans",
    );
    expect(review).toHaveTextContent(`3 ${en.home.toReview_other}`);
    expect(within(review).getByRole("link", { name: /Physics test/ })).toHaveAttribute(
      "href",
      "/exams/8/queue",
    );
    expect(confirmed).toHaveTextContent(`2 ${en.home.confirmedScripts_other}`);
  });
});

describe("language", () => {
  it("switches the sign-in page to French before signing in", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [401, { code: "auth.required" }]);
    const user = userEvent.setup();
    renderApp("/signin");

    await user.selectOptions(await screen.findByLabelText(en.language.label), "fr");

    expect(screen.getByRole("heading", { name: fr.signIn.title })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("fr");
  });

  it("uses the signed-in user's saved language", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me("teacher", "fr")]);
    api.on("GET /api/exams", [200, []]);
    api.on("GET /api/subjects", [200, []]);

    renderApp("/");

    expect(await screen.findByRole("heading", { name: fr.home.title })).toBeInTheDocument();
  });

  it("saves a language change for the signed-in user with the CSRF token", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me()]);
    api.on("GET /api/exams", [200, []]);
    api.on("GET /api/subjects", [200, []]);
    api.on("PUT /api/auth/me/language", [200, me("teacher", "fr")]);
    const user = userEvent.setup();
    renderApp("/");

    await user.selectOptions(await screen.findByLabelText(en.language.label), "fr");

    const call = api.calls.find((c) => c.path === "/api/auth/me/language");
    expect(call?.body).toEqual({ preferred_language: "fr" });
    expect(call?.headers["X-CSRF-Token"]).toBe("csrf-123");
  });
});

describe("roles", () => {
  it("hides admin navigation from teachers and blocks admin pages", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me("teacher")]);

    renderApp("/admin/users");

    expect(await screen.findByRole("alert")).toHaveTextContent(en.errors.auth.admin_required);
    expect(screen.queryByRole("link", { name: en.nav.users })).not.toBeInTheDocument();
  });

  it("shows the school's administration to administrators", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me("admin")]);

    renderApp("/settings");

    expect(await screen.findByRole("link", { name: new RegExp(en.nav.users) })).toBeInTheDocument();
    const rail = screen.getByRole("navigation", { name: en.nav.label });
    expect(within(rail).getByRole("link", { name: en.nav.classes })).toBeInTheDocument();
  });

  it("keeps classes out of a teacher's side rail", async () => {
    const api = fakeApi();
    api.on("GET /api/auth/me", [200, me("teacher")]);

    renderApp("/settings");

    const rail = await screen.findByRole("navigation", { name: en.nav.label });
    expect(within(rail).queryByRole("link", { name: en.nav.classes })).not.toBeInTheDocument();
    expect(within(rail).getByRole("link", { name: en.nav.queue })).toBeInTheDocument();
    expect(screen.queryByText(en.settings.adminTitle)).not.toBeInTheDocument();
  });
});

describe("translations", () => {
  function keys(value: unknown, prefix = ""): string[] {
    if (typeof value !== "object" || value === null) return [prefix];
    return Object.entries(value).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k));
  }

  it("French has exactly the same keys as English", () => {
    expect(keys(fr).sort()).toEqual(keys(en).sort());
  });
});
