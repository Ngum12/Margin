import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { fakeApi } from "../test/fakeApi";
import { PrintControls, PrintQueue } from "./SchoolHardware";

it("prints the selected confirmed students rather than the whole exam", async () => {
  const api = fakeApi();
  api.on("GET /api/print-jobs", [200, []]);
  api.on("POST /api/print-jobs", [201, { id: 1, status: "queued" }]);
  render(
    <PrintControls
      examId={7}
      students={[
        { id: 2, name: "Student A" },
        { id: 3, name: "Student B" },
      ]}
    />,
  );
  const user = userEvent.setup();
  await user.click(screen.getByText("Choose students"));
  await user.click(screen.getByRole("checkbox", { name: "Student B" }));
  await user.click(screen.getByRole("button", { name: "Print selected" }));
  await waitFor(() => {
    expect(api.calls.find((call) => call.method === "POST")?.body).toMatchObject({
      exam_id: 7,
      script_ids: [3],
      kind: "feedback",
    });
  });
});

it("requires checking printer output before retrying an uncertain submission", async () => {
  const api = fakeApi();
  api.on("GET /api/print-jobs", [
    200,
    [{ id: 9, exam_id: 7, status: "unknown", error_code: "hardware.print_uncertain" }],
  ]);
  api.on("POST /api/print-jobs/9/retry", [200, { id: 9, status: "queued" }]);
  render(<PrintQueue examId={7} />);
  const retry = await screen.findByRole("button", { name: "Retry" });
  expect(retry).toBeDisabled();
  const user = userEvent.setup();
  await user.click(screen.getByRole("checkbox"));
  await user.click(retry);
  expect(api.calls.find((call) => call.method === "POST")?.body).toEqual({
    acknowledge_uncertain: true,
  });
});
