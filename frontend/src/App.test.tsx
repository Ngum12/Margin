import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import en from "./i18n/locales/en.json";
import fr from "./i18n/locales/fr.json";

function mockFetch(response: Response | Error) {
  const fetchMock = vi.fn<typeof fetch>(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App", () => {
  it("shows the server version when the backend is healthy", async () => {
    const fetchMock = mockFetch(jsonResponse({ status: "ok", version: "1.2.3" }));

    render(<App />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(en.app.title);
    expect(await screen.findByText(/version 1\.2\.3/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.anything());
  });

  it("explains in plain language when the backend is unreachable", async () => {
    mockFetch(new TypeError("Failed to fetch"));

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent(en.status.unavailable);
  });

  it("treats an error status as unavailable", async () => {
    mockFetch(jsonResponse({ detail: "boom" }, 500));

    render(<App />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("switches the interface to French", async () => {
    mockFetch(jsonResponse({ status: "ok", version: "1.2.3" }));
    const user = userEvent.setup();

    render(<App />);
    await user.selectOptions(screen.getByRole("combobox"), "fr");

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(fr.app.title);
    expect(document.documentElement.lang).toBe("fr");
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
