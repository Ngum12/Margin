// Browser tests of the teacher review (Phase 4), against the seed in scripts/e2e_server.py:
// exam 1 with scripts 1 (AAAAAA, plain), 2 (BBBBBB, auto-rotated page and a deduction) and
// 3 (CCCCCC, manual marking). Tests run in order in one browser worker.

import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const PASSWORD = "correct-horse-battery";

async function signIn(page: Page, username: string) {
  await page.goto("/signin");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Your exams" })).toBeVisible();
}

function pageImage(page: Page) {
  return page.locator("img.viewer-image");
}

test("the queue shows the most uncertain script first", async ({ page }) => {
  await signIn(page, "alice");
  await page.goto("/exams/1/queue");
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(3);
  // The seed is marked by the Mock: labelled as test-model output (owner, 2026-10-15).
  await expect(page.getByRole("alert")).toContainText("read or marked by the test model");
  await expect(rows.nth(0)).toContainText("Test model: not real AI marking");
  await expect(rows.nth(0)).toContainText("CCCCCC");
  await expect(rows.nth(0)).toContainText("could not propose valid marks");
  // Then by lowest confidence (equal here), then by student code.
  await expect(rows.nth(1)).toContainText("AAAAAA");
  await expect(rows.nth(2)).toContainText("BBBBBB");
  await expect(rows.nth(2)).toContainText("1 page turned automatically");
  await expect(rows.nth(2)).toContainText("AI deducted 1 on 1 point");
});

test("a teacher reviews and confirms a script using only the keyboard", async ({ page }) => {
  await signIn(page, "alice");
  await page.goto("/exams/1/review/1");
  await expect(page.getByRole("heading", { name: /Ama Fon/ })).toBeVisible();
  const focused = page.locator("li.point-focused");
  const confirm = page.getByRole("button", { name: "Confirm script" });
  await expect(confirm).toBeDisabled();

  await page.keyboard.press("a"); // accept the first point
  await expect(focused.getByRole("button", { name: "1", pressed: true })).toBeVisible();
  await page.keyboard.press("j");
  await page.keyboard.press("0"); // second point: no marks
  await expect(focused.getByRole("button", { name: "0", pressed: true })).toBeVisible();
  await page.keyboard.press("c"); // change its category
  await expect(focused.getByRole("combobox")).toHaveValue("conceptual_error");
  await page.keyboard.press("m");
  await page.keyboard.type("Name a second property.");
  await page.keyboard.press("Escape"); // leave the box; the comment is saved
  await page.keyboard.press("Shift+A"); // accept the rest
  await expect(page.getByText("Accepted 1 AI proposal.")).toBeVisible();
  await expect(page.getByText("3 of 3 points decided")).toBeVisible();
  await expect(confirm).toBeEnabled();
  await page.keyboard.press("Control+Enter");

  await expect(page.getByText("Script confirmed.")).toBeVisible();
  await expect(page.getByText("Total: 2 / 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Reopen for changes" })).toBeVisible();
  await page.reload();
  await expect(page.locator(".badge-script-confirmed")).toHaveText("Confirmed");
  await expect(
    page.getByRole("textbox", { name: /Comment for this question/ }).first(),
  ).toHaveValue("Name a second property.");
});

test("rotate a page and undo an automatic rotation", async ({ page }) => {
  await signIn(page, "alice");
  await page.goto("/exams/1/review/2");
  await expect(page.getByText("Auto-rotated")).toBeVisible();
  await expect(pageImage(page)).toHaveAttribute("data-rotation", "180");
  // The AI deduction is easy to spot, and `d` jumps to it.
  await expect(page.locator(".deduction-badge")).toHaveText("−1");
  await page.keyboard.press("d");
  await expect(page.locator("li.point-focused .deduction-badge")).toBeVisible();

  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(pageImage(page)).toHaveAttribute("data-rotation", "0");
  await expect(page.getByText("Auto-rotated")).toBeHidden();
  await page.keyboard.press("r");
  await expect(pageImage(page)).toHaveAttribute("data-rotation", "90");
  await expect(pageImage(page)).toHaveCSS("transform", /matrix/);

  await page.reload();
  await expect(pageImage(page)).toHaveAttribute("data-rotation", "90");
  await expect(page.getByText(/turned after it was transcribed/)).toBeVisible();
  const loaded = await pageImage(page).evaluate(
    (img) => img instanceof HTMLImageElement && img.complete && img.naturalWidth > 0,
  );
  expect(loaded).toBe(true);
});

test("mark a manual-marking script", async ({ page }) => {
  await signIn(page, "alice");
  await page.goto("/exams/1/review/3");
  await expect(page.getByText(/Mark this script by hand/)).toBeVisible();
  await expect(page.getByText("No AI proposal: enter the marks yourself.").first()).toBeVisible();

  for (const key of ["1", "j", "1", "j", "1"]) await page.keyboard.press(key);
  await expect(page.getByText("3 of 3 points decided")).toBeVisible();
  await page.keyboard.press("Control+Enter");
  await expect(page.getByText("Script confirmed.")).toBeVisible();
  await expect(page.getByText("Total: 3 / 3")).toBeVisible();
});

test("results, CSV and marked PDFs for the confirmed scripts", async ({ page }) => {
  await signIn(page, "alice");
  await page.goto("/exams/1/results");
  await expect(page.getByText("Confirmed: 2 of 3 scripts")).toBeVisible();

  const [csv] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Download results (CSV)" }).click(),
  ]);
  expect(csv.suggestedFilename()).toBe("results-mock-exam-1.csv");
  const text = await readFile(await csv.path(), "utf-8");
  expect(text).toContain("AAAAAA");
  expect(text).toContain("CCCCCC");
  expect(text).not.toContain("BBBBBB"); // not confirmed
  expect(text).toContain("Test model: not real AI marking");

  const [pdf] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Marked PDF for AAAAAA" }).click(),
  ]);
  expect(pdf.suggestedFilename()).toBe("mock-exam-1-AAAAAA.pdf");
  expect((await readFile(await pdf.path())).subarray(0, 5).toString()).toBe("%PDF-");

  // The class file is built by the worker in the background.
  await page.getByRole("button", { name: /Prepare marked PDFs for the class/ }).click();
  const ready = page.getByRole("link", { name: "Download mock-exam-1-marked-scripts.pdf" });
  await expect(ready).toBeVisible({ timeout: 30_000 });
});

test("the review screen in French", async ({ page }) => {
  await signIn(page, "alice");
  await page.goto("/exams/1/review/2");
  await page.getByLabel("Language").selectOption("fr");
  await expect(page.getByRole("button", { name: "Confirmer la copie" })).toBeVisible();
  await expect(page.getByText("Raccourcis clavier")).toBeVisible();
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog", { name: "Raccourcis clavier" })).toContainText(
    "Critère suivant où l'IA a retiré des points",
  );
  await page.keyboard.press("Escape");
  // Back to English for the teacher's later sessions.
  await page.getByLabel("Langue").selectOption("en");
  await expect(page.getByRole("button", { name: "Confirm script" })).toBeVisible();
});

test("check pages, start AI marking and follow its progress", async ({ page }) => {
  await signIn(page, "alice");
  await page.goto("/exams/2/queue");
  const start = page.getByRole("button", { name: "Start AI marking" });
  await expect(page.getByText(/Check page orientation first/)).toBeVisible();
  await expect(start).toBeDisabled();

  const thumb = page.getByAltText("AAAAAA, page 2");
  await expect(thumb).toHaveAttribute("data-rotation", "0");
  await page.getByRole("button", { name: "Turn AAAAAA page 2 right" }).click();
  await expect(thumb).toHaveAttribute("data-rotation", "90");
  await page.getByRole("button", { name: "Turn AAAAAA page 2 left" }).click();
  await expect(thumb).toHaveAttribute("data-rotation", "0");
  await page.getByRole("button", { name: "All pages are upright: pages checked" }).click();

  await expect(start).toBeEnabled();
  await start.click();
  // The Mock model is quick: the run may finish before a poll sees it running.
  await expect(page.getByText("AI marking finished.")).toBeVisible({ timeout: 30_000 });
  await expect(page).toHaveTitle("✓ 1 ready · Margin");
});

test("another teacher cannot open the script", async ({ page }) => {
  await signIn(page, "bruno");
  await page.goto("/exams/1/review/1");
  await expect(
    page.getByText("This item does not exist, or you do not have access to it."),
  ).toBeVisible();
  await expect(page.locator("img.viewer-image")).toHaveCount(0);
});
