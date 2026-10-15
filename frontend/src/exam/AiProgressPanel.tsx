import { useEffect, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { api } from "../api/endpoints";
import type { AiProgress } from "../api/types";

const POLL_MS = 3000;
// While idle, look now and then so a run started elsewhere (another tab, the CLI) appears.
const IDLE_POLL_MS = 10000;

/** Live AI progress (owner, 2026-10-15): a bar counted in pages and questions, the time left
 * from measured calls, the page being read with the latest transcription ("watch it read"),
 * and a signal in the tab title when the work is done. */
export function AiProgressPanel({
  examId,
  started,
  onUpdate,
  onFinished,
}: {
  examId: number;
  // Increases when the teacher starts a run here: look at once and expect work (a quick run can
  // finish before the next regular look).
  started: number;
  onUpdate: (progress: AiProgress) => void;
  onFinished: () => void;
}) {
  const { t } = useTranslation();
  const [progress, setProgress] = useState<AiProgress | null>(null);
  // Which run the "finished" message belongs to: a new run started here hides the old one.
  const [finished, setFinished] = useState<{ ready: number; manual: number; run: number } | null>(
    null,
  );
  const wasRunning = useRef(false);
  const callbacks = useRef({ onUpdate, onFinished });
  useEffect(() => {
    callbacks.current = { onUpdate, onFinished };
  });

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    if (started > 0) wasRunning.current = true;
    const poll = () => {
      api
        .aiProgress(examId)
        .then((next) => {
          if (cancelled) return;
          setProgress(next);
          callbacks.current.onUpdate(next);
          if (wasRunning.current && !next.running) {
            setFinished({ ready: next.ready, manual: next.manual, run: started });
            callbacks.current.onFinished();
          }
          wasRunning.current = next.running;
          timer = window.setTimeout(poll, next.running ? POLL_MS : IDLE_POLL_MS);
        })
        .catch(() => {
          if (!cancelled) timer = window.setTimeout(poll, IDLE_POLL_MS);
        });
    };
    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [examId, started]);

  // Finished signal in the tab title, so a teacher in another tab sees it.
  useEffect(() => {
    if (!finished) return;
    const before = document.title;
    document.title = t("progress.tabTitle", { count: finished.ready });
    return () => {
      document.title = before;
    };
  }, [finished, t]);

  const done = finished?.run === started ? finished : null;
  if (done && progress && !progress.running) {
    return (
      <div className="card progress-done" role="status">
        <strong>{t("progress.finished")}</strong>{" "}
        {t("progress.finishedCounts", { ready: done.ready, manual: done.manual })}
      </div>
    );
  }
  if (!progress?.running) return null;

  const current = progress.scripts.find((s) => s.state === "working");
  return (
    <div className="card progress-card">
      <h2>{t("progress.title")}</h2>
      <div
        className="progress-bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress.percent}
        aria-label={t("progress.title")}
      >
        <div className="progress-fill" style={{ width: `${String(progress.percent)}%` }} />
      </div>
      <p aria-live="polite">
        <strong>{progress.percent}%</strong>
        {current?.step && current.index && current.total
          ? ` · ${t(`progress.step.${current.step}`, {
              code: current.student_code,
              index: current.index,
              total: current.total,
            })}`
          : ` · ${t("progress.waiting")}`}
        {" · "}
        <span className="muted">{eta(t, progress.eta_seconds)}</span>
      </p>
      <div className="watch-read">
        {progress.current_page_id !== null && (
          <figure>
            <img
              src={api.pageImageUrl(progress.current_page_id, "thumb")}
              alt={t("progress.readingNow", { code: progress.current_student ?? "" })}
            />
            <figcaption className="muted small">
              {t("progress.readingNow", { code: progress.current_student ?? "" })}
            </figcaption>
          </figure>
        )}
        {progress.latest_read && (
          <div className="watch-read-text">
            <p className="muted small">
              {t("progress.latestRead", { code: progress.latest_read.student_code })}
            </p>
            <pre className="transcription-text">{tail(progress.latest_read.text)}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

function tail(text: string, length = 600): string {
  return text.length > length ? `…${text.slice(-length)}` : text;
}

function eta(t: TFunction, seconds: number | null): string {
  if (seconds === null) return t("progress.estimating");
  if (seconds < 60) return t("progress.underAMinute");
  return t("progress.minutesLeft", { count: Math.round(seconds / 60) });
}
