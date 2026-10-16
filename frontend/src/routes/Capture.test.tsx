import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";
import { fakeApi } from "../test/fakeApi";
import Capture from "./Capture";

it("requires the teacher to accept a prepared photograph", async () => {
  const api = fakeApi();
  const photo = {
    id: 4,
    status: "capture_preview",
    error_code: null,
    prepared: true,
    options: {
      left: 0,
      top: 0,
      right: 1,
      bottom: 1,
      angle: 0,
      auto_crop: true,
      auto_straighten: true,
      clean: true,
    },
  };
  api.on("GET /api/capture", [200, [photo]]);
  api.on("GET /api/intake", [200, { pages: [], quarantine: [], batches: [] }]);
  api.on("POST /api/capture/4/accept", [200, { ...photo, status: "pending" }]);
  render(
    <MemoryRouter>
      <Capture />
    </MemoryRouter>,
  );
  const use = await screen.findByRole("button", { name: "Use this page" });
  expect(api.calls.filter((call) => call.method === "POST")).toHaveLength(0);
  expect(screen.getByRole("img", { name: "Prepared page" })).toBeInTheDocument();
  await userEvent.setup().click(use);
  await waitFor(() => {
    expect(api.calls.some((call) => call.path === "/api/capture/4/accept")).toBe(true);
  });
});
