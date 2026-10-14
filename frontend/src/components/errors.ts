import type { TFunction } from "i18next";

import { ApiError } from "../api/client";
import type { Issue } from "../api/types";

/** Plain-language, translated message for any error thrown by the API client. */
export function errorMessage(t: TFunction, error: unknown): string {
  const code = error instanceof ApiError ? error.code : "server.error";
  return t(`errors.${code}`, { defaultValue: t("errors.generic") });
}

/** Translated text for one validation issue (server or client side, same codes). */
export function issueMessage(t: TFunction, issue: Issue): string {
  // CSV import issues carry their row in the path: ["row", 7].
  const row = issue.path[0] === "row" ? { row: issue.path[1] } : {};
  return t(`issues.${issue.code}`, { ...issue.params, ...row, defaultValue: t("issues.unknown") });
}
