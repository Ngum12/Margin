// All requests are same-origin. Never pass absolute URLs to another host.

export interface Health {
  status: "ok";
  version: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson(path: `/api/${string}`, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    ...(signal ? { signal } : {}),
  });
  if (!response.ok) {
    throw new ApiError(response.status, `Request to ${path} failed`);
  }
  return response.json();
}

function isHealth(value: unknown): value is Health {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as Record<string, unknown>).status === "ok" &&
    typeof (value as Record<string, unknown>).version === "string"
  );
}

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const data = await getJson("/api/health", signal);
  if (!isHealth(data)) {
    throw new ApiError(500, "Unexpected health response");
  }
  return data;
}
