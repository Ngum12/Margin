import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { api } from "../api/endpoints";
import { ErrorMessage, Loading, StatusBadge } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { useSubjectName } from "../exam/subjects";

export default function Home() {
  const { t } = useTranslation();
  const { state } = useLoad(() => api.exams(), []);
  const subjectName = useSubjectName();

  return (
    <section>
      <div className="section-header">
        <h1>{t("home.title")}</h1>
        <Link className="button" to="/exams/new">
          {t("home.newExam")}
        </Link>
      </div>
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorMessage error={state.error} />}
      {state.status === "ready" && state.data.length === 0 && (
        <p className="card muted">{t("home.empty")}</p>
      )}
      {state.status === "ready" && state.data.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("exam.title")}</th>
                <th>{t("exam.class")}</th>
                <th>{t("exam.subject")}</th>
                <th>{t("exam.date")}</th>
                <th>{t("exam.status")}</th>
                <th className="num">{t("home.totalMarks")}</th>
                <th className="num">{t("home.waiting")}</th>
                <th className="num">{t("home.aiMarked")}</th>
                <th className="num">{t("home.confirmed")}</th>
              </tr>
            </thead>
            <tbody>
              {state.data.map((exam) => (
                <tr key={exam.id}>
                  <td>
                    <Link to={`/exams/${String(exam.id)}`}>{exam.title}</Link>
                  </td>
                  <td>{exam.class_name}</td>
                  <td>{subjectName(exam.subject_code)}</td>
                  <td>{exam.exam_date ?? "—"}</td>
                  <td>
                    <StatusBadge status={exam.status} />
                  </td>
                  <td className="num">{exam.total_marks}</td>
                  <td className="num">{exam.scripts.waiting}</td>
                  <td className="num">{exam.scripts.ai_marked}</td>
                  <td className="num">{exam.scripts.confirmed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
