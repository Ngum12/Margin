// Same-origin JSON client. Never pass absolute URLs to another host.

import type { Issue } from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly issues: Issue[] = [],
  ) {
    super(code);
    this.name = "ApiError";
  }
}

let csrfToken: string | null = null;
let sessionUserId: number | null = null;

export function setCsrfToken(token: string | null, userId: number | null = null): void {
  csrfToken = token;
  sessionUserId = userId;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

interface RequestOptions {
  json?: unknown;
  text?: string;
  file?: Blob;
  contentType?: string;
  headers?: Record<string, string>;
}

function isErrorBody(value: unknown): value is { code: string; issues?: Issue[] } {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>).code === "string"
  );
}

/**
 * A tab opened before signing in again (in another tab, or after a restart) still holds the old
 * session's CSRF token, so every change it sends is refused although pages still load. Fetch the
 * current token once and retry, but only when the cookie still belongs to the same user: if
 * someone else signed in, never act as them.
 */
async function refreshCsrfToken(): Promise<boolean> {
  try {
    const response = await fetch("/api/auth/me", {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) return false;
    const me = (await response.json()) as { csrf_token?: string; user?: { id?: number } };
    if (typeof me.csrf_token !== "string") return false;
    if (sessionUserId !== null && me.user?.id !== sessionUserId) {
      throw new ApiError(403, "auth.session_changed");
    }
    csrfToken = me.csrf_token;
    return true;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    return false;
  }
}

export async function request<T>(
  method: Method,
  path: `/api/${string}`,
  options: RequestOptions = {},
): Promise<T> {
  try {
    return await send<T>(method, path, options);
  } catch (err) {
    const stale =
      err instanceof ApiError &&
      err.code === "auth.csrf_failed" &&
      method !== "GET" &&
      !path.startsWith("/api/auth/");
    if (stale && (await refreshCsrfToken())) return send<T>(method, path, options);
    throw err;
  }
}

async function send<T>(
  method: Method,
  path: `/api/${string}`,
  options: RequestOptions,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  let body: string | Blob | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.text !== undefined) {
    headers["Content-Type"] = options.contentType ?? "text/plain";
    body = options.text;
  } else if (options.file !== undefined) {
    headers["Content-Type"] = options.contentType ?? "application/octet-stream";
    body = options.file;
  }
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      ...(body !== undefined ? { body } : {}),
    });
  } catch {
    throw new ApiError(0, "network.unreachable");
  }

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (isErrorBody(data)) throw new ApiError(response.status, data.code, data.issues ?? []);
    throw new ApiError(response.status, "server.error");
  }
  return data as T;
}
