import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/endpoints";
import type { ExportJob } from "../../api/types";
import { ErrorMessage, Loading } from "../../components/ui";
import { useLoad } from "../../components/useLoad";
import { ExportJobList } from "../../exam/ExportJobs";
import { useSubjectName } from "../../exam/subjects";

/** Admin (screen 9): model configuration and status, and the training-data export
 * (brief section 8): confirmed scripts of consenting students only, codes only, no names. */
export default function TrainingData() {
  const { t } = useTranslation();
  const { state } = useLoad(
    () => Promise.all([api.trainingExport(), api.modelConfig(), api.systemStatus()]),
    [],
  );
  const subjectName = useSubjectName();
  const [selected, setSelected] = useState<Set<number> | null>(null);
  const [jobs, setJobs] = useState<ExportJob[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (state.status === "error") return <ErrorMessage error={state.error} />;
  if (state.status === "loading") return <Loading />;
  const [preview, config, status] = state.data;
  const chosen =
    selected ?? new Set(preview.exams.filter((e) => e.consented > 0).map((e) => e.exam_id));
  const shownJobs = jobs ?? preview.exports;
  const consented = preview.exams
    .filter((e) => chosen.has(e.exam_id))
    .reduce((sum, e) => sum + e.consented, 0);

  async function exportNow() {
    setBusy(true);
    setError(null);
    try {
      const job = await api.requestTrainingExport([...chosen]);
      setJobs([job, ...shownJobs]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function toggle(examId: number) {
    const next = new Set(chosen);
    if (next.has(examId)) next.delete(examId);
    else next.add(examId);
    setSelected(next);
  }

  return (
    <section>
      <h1>{t("trainingData.title")}</h1>

      <div className="card">
        <h2>{t("trainingData.modelTitle")}</h2>
        <dl className="facts">
          <dt>{t("trainingData.backend")}</dt>
          <dd>{config.ai_backend}</dd>
          <dt>{t("trainingData.modelHost")}</dt>
          <dd className="code">{config.model_host}</dd>
          <dt>{t("trainingData.readerModel")}</dt>
          <dd>
            {config.reader_model}{" "}
            <span className="muted">
              (
              {status.reader_model_installed
                ? t("trainingData.installed")
                : t("trainingData.missing")}
              )
            </span>
          </dd>
          <dt>{t("trainingData.markerModel")}</dt>
          <dd>
            {config.marker_model} · {t(`trainingData.evidence.${config.marker_evidence}`)}
          </dd>
          <dt>{t("trainingData.timeout")}</dt>
          <dd>{t("trainingData.seconds", { count: config.model_timeout_seconds })}</dd>
          <dt>{t("trainingData.orientation")}</dt>
          <dd>{t(`trainingData.orientationCheck.${config.orientation_check}`)}</dd>
          <dt>{t("trainingData.status")}</dt>
          <dd>
            {status.worker_online ? t("trainingData.workerOnline") : t("ai.workerOffline")}
            {" · "}
            {status.model_server_reachable
              ? t("trainingData.serverReachable")
              : t("ai.modelServerDown")}
          </dd>
        </dl>
        <p className="muted small">{t("trainingData.configHelp")}</p>
      </div>

      <div className="card">
        <h2>{t("trainingData.exportTitle")}</h2>
        <p className="muted">{t("trainingData.exportHelp")}</p>
        {preview.exams.length === 0 ? (
          <p className="muted">{t("trainingData.noConfirmed")}</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">
                    <span className="visually-hidden">{t("trainingData.include")}</span>
                  </th>
                  <th scope="col">{t("exam.title")}</th>
                  <th scope="col">{t("exam.subject")}</th>
                  <th scope="col" className="num">
                    {t("trainingData.confirmed")}
                  </th>
                  <th scope="col" className="num">
                    {t("trainingData.consented")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {preview.exams.map((exam) => (
                  <tr key={exam.exam_id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={t("trainingData.includeExam", { title: exam.title })}
                        checked={chosen.has(exam.exam_id)}
                        disabled={exam.consented === 0}
                        onChange={() => {
                          toggle(exam.exam_id);
                        }}
                      />
                    </td>
                    <td>{exam.title}</td>
                    <td>{subjectName(exam.subject_code)}</td>
                    <td className="num">{exam.confirmed}</td>
                    <td className="num">{exam.consented}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="actions">
          <button type="button" disabled={busy || consented === 0} onClick={() => void exportNow()}>
            {t("trainingData.export", { count: consented })}
          </button>
        </div>
        <ErrorMessage error={error} />
        <ExportJobList jobs={shownJobs} />
        <p className="muted small">{t("trainingData.privacy")}</p>
      </div>
    </section>
  );
}
