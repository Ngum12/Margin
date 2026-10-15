import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/endpoints";
import type { ExportJob } from "../api/types";

const POLL_MS = 2000;

/** Files built in the background: follow each until it is ready, then offer the download. */
export function ExportJobList({ jobs }: { jobs: ExportJob[] }) {
  if (jobs.length === 0) return null;
  return (
    <ul className="plain-list">
      {jobs.map((job) => (
        <ExportJobRow key={job.id} job={job} />
      ))}
    </ul>
  );
}

function ExportJobRow({ job: initial }: { job: ExportJob }) {
  const { t } = useTranslation();
  // Rows are keyed by export id, so the starting value never changes for a row.
  const [job, setJob] = useState(initial);

  useEffect(() => {
    if (job.status !== "pending") return;
    const timer = window.setInterval(() => {
      api
        .exportStatus(job.id)
        .then(setJob)
        .catch(() => {
          // Keep polling; the status is shown again on the next tick.
        });
    }, POLL_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [job.id, job.status]);

  const when = new Date(job.created_at).toLocaleString();
  return (
    <li>
      {job.status === "done" ? (
        <a href={api.exportFileUrl(job.id)} download={job.filename ?? undefined}>
          {t("exports.download", { name: job.filename ?? "" })}
        </a>
      ) : job.status === "pending" ? (
        <span role="status">{t("exports.preparing")}</span>
      ) : (
        <span className="error">
          {t(`errors.${job.error_code ?? "export.failed"}`, {
            defaultValue: t("errors.export.failed"),
          })}
        </span>
      )}{" "}
      <span className="muted small">
        {when}
        {job.size_bytes ? ` · ${formatSize(job.size_bytes)}` : ""}
      </span>
    </li>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${String(Math.max(1, Math.round(bytes / 1024)))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
