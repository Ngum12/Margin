import { AnswerSheets } from "../components/AnswerSheets";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";

import { api } from "../api/endpoints";
import { ErrorMessage, Loading } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { ExamHeader } from "../exam/ExamHeader";

export default function CoverSheets() {
  const { t } = useTranslation();
  const examId = Number(useParams().examId);
  const { state, set } = useLoad(
    () => Promise.all([api.exam(examId), api.coverSheets(examId)]),
    [examId],
  );
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorMessage error={state.error} />;
  const [exam, rows] = state.data;
  const prepared = rows.length > 0 && rows.every((r) => r.has_sheet);

  async function prepare() {
    setBusy(true);
    setError(null);
    try {
      set([exam, await api.prepareCoverSheets(examId)]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <ExamHeader exam={exam} />
      {exam.status === "draft" ? (
        <p className="card">{t("sheets.needReady")}</p>
      ) : rows.length === 0 ? (
        <p className="card">{t("sheets.noStudents")}</p>
      ) : (
        <>
          <AnswerSheets examId={examId} />
          <div className="card">
            <p>{t("sheets.help")}</p>
            <ErrorMessage error={error} />
            <div className="actions">
              {!prepared && (
                <button type="button" disabled={busy} onClick={() => void prepare()}>
                  {t("sheets.prepare", { count: rows.filter((r) => !r.has_sheet).length })}
                </button>
              )}
              {rows.some((r) => r.has_sheet) && (
                <a
                  className={prepared ? "button" : "button button-secondary"}
                  href={api.coverSheetsPdfUrl(examId)}
                  download
                >
                  {t("sheets.download")}
                </a>
              )}
            </div>
            <p className="muted">{t("sheets.privacy")}</p>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("students.code")}</th>
                  <th>{t("students.name")}</th>
                  <th>{t("sheets.sheet")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.student_id}>
                    <td className="code">{row.code}</td>
                    <td>{row.display_name ?? <span className="muted">—</span>}</td>
                    <td>{row.has_sheet ? t("sheets.ready") : t("sheets.notYet")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
