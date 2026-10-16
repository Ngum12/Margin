import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import { api } from "../api/endpoints";
import type { AiProgress, Queue as QueueData, QueueItem } from "../api/types";
import { ErrorMessage, Loading } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { AiPanel } from "../exam/AiPanel";
import { AiProgressPanel } from "../exam/AiProgressPanel";
import { Icon } from "../components/Icon";
import { ExamHeader } from "../exam/ExamHeader";
import { PageCheck } from "../exam/PageCheck";
import { minutesSeconds } from "../review/focus";
import { ConfirmButton, TestModelBadge, TestModelBanner } from "../review/ModelLabel";

const LOW_CONFIDENCE = 0.6;

/** Screen 6: the class's scripts, most uncertain first, with AI progress and review time. */
export default function Queue() {
  const { t } = useTranslation();
  const examId = Number(useParams().examId);
  const { state, reload } = useLoad(() => api.queue(examId), [examId]);
  const check = useLoad(() => api.pageCheck(examId), [examId]);
  const [progress, setProgress] = useState<AiProgress | null>(null);
  const [started, setStarted] = useState(0);
  const runStarted = () => {
    setStarted((n) => n + 1);
  };

  if (state.status === "error") return <ErrorMessage error={state.error} />;
  if (state.status === "loading") return <Loading />;
  const queue = state.data;
  const exam = { id: queue.exam_id, title: queue.exam_title, status: queue.exam_status };

  return (
    <section>
      <ExamHeader exam={exam} />
      {queue.exam_status === "draft" ? (
        <p className="panel empty-state">{t("sheets.needReady")}</p>
      ) : (
        <>
          {check.state.status === "ready" && (
            <PageCheck data={check.state.data} onChange={check.set} />
          )}
          <AiPanel
            examId={examId}
            onProgress={reload}
            pagesChecked={check.state.status === "ready" && check.state.data.checked_at !== null}
            onStarted={runStarted}
          />
          <AiProgressPanel
            examId={examId}
            started={started}
            onUpdate={setProgress}
            onFinished={reload}
          />
          <div className="panel">
            <h2>{t("queue.title")}</h2>
            <p className="muted">{t("queue.help")}</p>
            {queue.test_model_count > 0 && <TestModelBanner count={queue.test_model_count} />}
            <RerunExam
              examId={examId}
              queue={queue}
              onDone={() => {
                reload();
                runStarted();
              }}
            />
            <p>
              {t("queue.confirmedCount", {
                confirmed: queue.confirmed_count,
                count: queue.items.length,
              })}
            </p>
            <ReviewTime
              count={queue.timed_count}
              wall={queue.average_review_seconds}
              active={queue.average_active_seconds}
            />
            {queue.items.length === 0 ? (
              <p className="empty-state">{t("queue.empty")}</p>
            ) : (
              <div className="table-wrap">
                <table className="data-table queue-table">
                  <thead>
                    <tr>
                      <th scope="col">{t("queue.student")}</th>
                      <th scope="col">{t("queue.status")}</th>
                      <th scope="col">{t("queue.checks")}</th>
                      <th scope="col">{t("queue.aiMarks")}</th>
                      <th scope="col">{t("queue.teacherMarks")}</th>
                      <th scope="col">{t("queue.reviewTime")}</th>
                      <th scope="col">
                        <span className="visually-hidden">{t("common.actions")}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {queue.items.map((item) => (
                      <QueueRow
                        key={item.script_id}
                        examId={examId}
                        item={item}
                        live={progress?.scripts.find((s) => s.script_id === item.script_id)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function RerunExam({
  examId,
  queue,
  onDone,
}: {
  examId: number;
  queue: QueueData;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  // Unconfirmed scripts the AI has finished with (or flagged): the ones a re-run would redo.
  const candidates = queue.items.filter((i) => i.reviewable && i.status !== "confirmed").length;
  if (candidates === 0) return null;
  return (
    <div className="actions">
      <ConfirmButton
        label={t("rerun.exam", { count: candidates })}
        question={t("rerun.examQuestion")}
        onConfirm={() => {
          setError(null);
          api
            .rerunExam(examId)
            .then((result) => {
              setMessage(t("rerun.examStarted", { count: result.scripts_queued }));
              onDone();
            })
            .catch(setError);
        }}
      />
      {message && <span role="status">{message}</span>}
      <ErrorMessage error={error} />
    </div>
  );
}

function Duration({ seconds }: { seconds: number }) {
  const { t } = useTranslation();
  return <>{t("queue.duration", minutesSeconds(seconds))}</>;
}

function ReviewTime({
  count,
  wall,
  active,
}: {
  count: number;
  wall: number | null;
  active: number | null;
}) {
  const { t } = useTranslation();
  if (count === 0 || wall === null || active === null) {
    return <p className="muted">{t("queue.noReviewTime")}</p>;
  }
  return (
    <p>
      {t("queue.averageTime", { count })} <Duration seconds={wall} />{" "}
      <span className="muted">
        ({t("queue.activeTime")} <Duration seconds={active} />)
      </span>
      <br />
      <span className="muted small">{t("queue.localOnly")}</span>
    </p>
  );
}

function QueueRow({
  examId,
  item,
  live,
}: {
  examId: number;
  item: QueueItem;
  live: AiProgress["scripts"][number] | undefined;
}) {
  const { t } = useTranslation();
  const checks = [
    item.manual_reason &&
      t(`ai.manualReason.${item.manual_reason}`, { defaultValue: t("ai.manualReason.unknown") }),
    item.uncertain_points > 0 && t("queue.uncertain", { count: item.uncertain_points }),
    item.min_confidence !== null &&
      item.min_confidence < LOW_CONFIDENCE &&
      t("queue.lowConfidence", { percent: Math.round(item.min_confidence * 100) }),
    item.page_count_flag && t(`queue.pageFlag.${item.page_count_flag}`),
    item.auto_rotated_pages > 0 && t("queue.autoRotated", { count: item.auto_rotated_pages }),
    item.deductions > 0 &&
      t("queue.deductions", { count: item.deductions, marks: item.marks_deducted }),
  ].filter((c): c is string => Boolean(c));
  const href = `/exams/${String(examId)}/review/${String(item.script_id)}`;

  return (
    <tr>
      <td>
        {item.student_name && <span className="strong-link">{item.student_name}</span>}{" "}
        <span className="code">{item.student_code}</span>
      </td>
      <td>
        <span className={`badge badge-script-${item.status}`}>
          {item.lifecycle ? t(`lifecycle.${item.lifecycle}`) : t(`scriptStatus.${item.status}`)}
          {item.printed && <> · {t("lifecycle.printed")}</>}
        </span>
        {item.test_model && (
          <>
            {" "}
            <TestModelBadge />
          </>
        )}
        {live?.state === "working" && live.step && live.index && live.total && (
          <span className="live-step small" role="status">
            {t(`progress.rowStep.${live.step}`, { index: live.index, total: live.total })}
          </span>
        )}
        {live?.state === "queued" && <span className="muted small"> · {t("progress.queued")}</span>}
      </td>
      <td>
        {checks.length > 0 ? (
          <ul className="plain-list small">
            {checks.map((check) => (
              <li key={check}>{check}</li>
            ))}
          </ul>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td>
        {item.proposed_total === null
          ? "—"
          : `${String(item.proposed_total)} / ${String(item.max_total)}`}
      </td>
      <td>
        {item.final_total === null
          ? "—"
          : `${String(item.final_total)} / ${String(item.max_total)}`}
        <br />
        <span className="muted small">
          {t("queue.decided", { decided: item.decided_points, total: item.total_points })}
        </span>
      </td>
      <td>{item.review_seconds === null ? "—" : <Duration seconds={item.review_seconds} />}</td>
      <td className="row-end">
        {item.reviewable ? (
          <Link
            to={href}
            className={
              item.status === "confirmed"
                ? "button button-secondary button-small"
                : "button button-small"
            }
          >
            {item.status === "confirmed" ? t("queue.open") : t("queue.review")}
            <Icon name="next" size={16} />
          </Link>
        ) : (
          <span className="muted">{t("queue.waitingForAi")}</span>
        )}
      </td>
    </tr>
  );
}
