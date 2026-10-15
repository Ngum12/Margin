import { afterEach, describe, expect, it } from "vitest";

import { fakeApi, me } from "../test/fakeApi";
import { ApiError, request, setCsrfToken } from "./client";

const csrfFailed: [number, unknown] = [403, { code: "auth.csrf_failed", detail: "x" }];

afterEach(() => {
  setCsrfToken(null);
});

describe("api client", () => {
  it("recovers once from a token left over from an earlier sign-in", async () => {
    const api = fakeApi();
    const current = me();
    setCsrfToken("old-token", current.user.id);
    api.on("GET /api/auth/me", [200, current]);
    api.on("POST /api/exams/7/pages/discard", () => {
      const last = api.calls[api.calls.length - 1];
      return last?.headers["X-CSRF-Token"] === current.csrf_token ? [204] : csrfFailed;
    });

    await request("POST", "/api/exams/7/pages/discard", { json: { page_ids: [1] } });

    const sent = api.calls.filter((c) => c.path === "/api/exams/7/pages/discard");
    expect(sent.map((c) => c.headers["X-CSRF-Token"])).toEqual(["old-token", current.csrf_token]);
  });

  it("never acts as another user who signed in from a different tab", async () => {
    const api = fakeApi();
    const other = me("admin");
    setCsrfToken("old-token", other.user.id + 1);
    api.on("GET /api/auth/me", [200, other]);
    api.on("POST /api/exams/7/pages/discard", csrfFailed);

    const error = await request("POST", "/api/exams/7/pages/discard", { json: {} }).catch(
      (e: unknown) => e,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("auth.session_changed");
    expect(api.calls.filter((c) => c.path === "/api/exams/7/pages/discard")).toHaveLength(1);
  });

  it("retries only once", async () => {
    const api = fakeApi();
    setCsrfToken("old-token", me().user.id);
    api.on("GET /api/auth/me", [200, me()]);
    api.on("POST /api/exams/7/pages/discard", csrfFailed);

    await expect(request("POST", "/api/exams/7/pages/discard", { json: {} })).rejects.toThrow(
      "auth.csrf_failed",
    );
    expect(api.calls.filter((c) => c.path === "/api/exams/7/pages/discard")).toHaveLength(2);
  });
});
