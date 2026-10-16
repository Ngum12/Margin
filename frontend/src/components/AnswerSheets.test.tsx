import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { fakeApi } from "../test/fakeApi";
import { AnswerSheets } from "./AnswerSheets";

it("restores the issued page count and prints directly with a request token", async () => {
  const api = fakeApi();
  api.on("GET /api/exams/7/answer-sheets", [200, { pages_per_student: 4 }]);
  api.on("GET /api/print-jobs", [200, []]);
  api.on("POST /api/exams/7/answer-sheets", [
    201,
    { status: "queued", download_url: "/api/print-jobs/1/sheets.pdf" },
  ]);
  render(<AnswerSheets examId={7} />);
  await waitFor(() => {
    expect(screen.getByRole("spinbutton", { name: "Pages per student" })).toHaveValue(4);
  });
  await userEvent.setup().click(screen.getByRole("button", { name: "Print answer sheets" }));
  await waitFor(() => {
    expect(api.calls.find((call) => call.method === "POST")?.body).toMatchObject({
      pages_per_student: 4,
      layout: "answer",
      send_to_printer: true,
    });
    expect(api.calls.find((call) => call.method === "POST")?.body).toHaveProperty("request_key");
  });
});
