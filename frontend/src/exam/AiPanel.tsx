import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/endpoints";
import { ErrorMessage } from "../components/ui";
import { useLoad } from "../components/useLoad";

const POLL_MS = 5000;

/** Start AI marking and follow its progress (on the marking queue, screen 6). */
export function AiPanel({
  examId,
  onProgress,
  pagesChecked,
  onStarted,
}: {
  examId: number;
  onProgress: () => void;
  pagesChecked: boolean;
  onStarted?: () => void;
}) {
  const { t } = useTranslation();
  const { state, reload } = useLoad(() => api.aiStatus(examId), [examId]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const status = state.status === "ready" ? state.data : null;
  const active = status ? status.jobs_queued + status.jobs_running > 0 : false;

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      reload();
      onProgress();
    }, POLL_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, [active, reload, onProgress]);

  if (state.status === "error") return <ErrorMessage error={state.error} />;
  if (!status) return null;

  const waiting = (status.scripts.waiting ?? 0) + (status.scripts.transcribed ?? 0);
  const system = status.system;
  const problems = [
    !system.worker_online && t("ai.workerOffline"),
    !system.model_server_reachable && t("ai.modelServerDown"),
    system.model_server_reachable &&
      !system.reader_model_installed &&
      t("ai.modelMissing", { model: system.reader_model }),
    system.model_server_reachable &&
      system.marker_model !== system.reader_model &&
      !system.marker_model_installed &&
      t("ai.modelMissing", { model: system.marker_model }),
  ].filter((p): p is string => Boolean(p));

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await api.startAiMarking(examId);
      reload();
      onStarted?.();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>{t("ai.title")}</h2>
      <p className="muted">{t("ai.help")}</p>
      {problems.map((problem) => (
        <p key={problem} className="warning-text" role="status">
          {problem}
        </p>
      ))}
      <p>
        {t("ai.progress", {
          waiting,
          marked: status.scripts.ai_marked ?? 0,
          flagged: status.flagged.length,
        })}
      </p>
      {active && (
        <p className="muted">
          {t("ai.running", { count: status.jobs_queued + status.jobs_running })}
        </p>
      )}
      {status.jobs_failed > 0 && (
        <p className="error">{t("ai.failedJobs", { count: status.jobs_failed })}</p>
      )}
      {!pagesChecked && (
        <p className="notice notice-warning" role="status">
          {t("pageCheck.firstNotice")} <a href="#page-check">{t("pageCheck.goTo")}</a>
        </p>
      )}
      <ErrorMessage error={error} />
      <div className="actions">
        <button
          type="button"
          disabled={!pagesChecked || busy || active || (waiting === 0 && status.jobs_failed === 0)}
          onClick={() => void start()}
        >
          {t("ai.start")}
        </button>
      </div>
      {status.flagged.length > 0 && (
        <>
          <h3>{t("ai.flaggedTitle")}</h3>
          <ul className="plain-list">
            {status.flagged.map((f) => (
              <li key={f.script_id}>
                <span className="code">{f.student_code}</span>:{" "}
                {t(`ai.manualReason.${f.reason}`, { defaultValue: t("ai.manualReason.unknown") })}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
