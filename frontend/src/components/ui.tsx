import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { ExamStatus, Issue } from "../api/types";
import { errorMessage, issueMessage } from "./errors";

export function ErrorMessage({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  return (
    <p className="error" role="alert">
      {errorMessage(t, error)}
    </p>
  );
}

export function IssueList({
  issues,
  tone,
  title,
}: {
  issues: Issue[];
  tone: "error" | "warning" | "info";
  title?: string;
}) {
  const { t } = useTranslation();
  if (issues.length === 0) return null;
  return (
    <div className={`issues issues-${tone}`} role={tone === "error" ? "alert" : "status"}>
      {title && <p className="issues-title">{title}</p>}
      <ul>
        {issues.map((issue, index) => (
          <li key={`${issue.code}-${String(index)}`}>{issueMessage(t, issue)}</li>
        ))}
      </ul>
    </div>
  );
}

export function StatusBadge({ status }: { status: ExamStatus }) {
  const { t } = useTranslation();
  return <span className={`badge badge-${status}`}>{t(`examStatus.${status}`)}</span>;
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export function Loading() {
  const { t } = useTranslation();
  return <p className="muted">{t("common.loading")}</p>;
}
