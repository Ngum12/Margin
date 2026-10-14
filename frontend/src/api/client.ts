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

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

interface RequestOptions {
  json?: unknown;
  text?: string;
  contentType?: string;
}

function isErrorBody(value: unknown): value is { code: string; issues?: Issue[] } {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>).code === "string"
  );
}

export async function request<T>(
  method: Method,
  path: `/api/${string}`,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: string | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.text !== undefined) {
    headers["Content-Type"] = options.contentType ?? "text/plain";
    body = options.text;
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
