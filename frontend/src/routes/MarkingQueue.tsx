import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { api } from "../api/endpoints";
import { Icon } from "../components/Icon";
import { ErrorMessage, Loading } from "../components/ui";
import { useLoad } from "../components/useLoad";

/** Every exam with scripts the teacher can review now, most waiting first. */
export default function MarkingQueue() {
  const { t } = useTranslation();
  const { state } = useLoad(() => api.exams(), []);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorMessage error={state.error} />;
  const exams = state.data
    .filter((e) => e.scripts.ai_marked > 0 || (e.status !== "draft" && e.scripts.waiting > 0))
    .sort((a, b) => b.scripts.ai_marked - a.scripts.ai_marked);

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>{t("markingQueue.title")}</h1>
          <p className="page-lede">{t("markingQueue.lede")}</p>
        </div>
      </header>
      {exams.length === 0 ? (
        <p className="panel empty-state">{t("markingQueue.empty")}</p>
      ) : (
        <div className="table-wrap panel">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">{t("exam.title")}</th>
                <th scope="col">{t("exam.class")}</th>
                <th scope="col" className="num">
                  {t("markingQueue.toReview")}
                </th>
                <th scope="col" className="num">
                  {t("markingQueue.withAi")}
                </th>
                <th scope="col" className="num">
                  {t("home.confirmed")}
                </th>
                <th scope="col">
                  <span className="visually-hidden">{t("common.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {exams.map((exam) => (
                <tr key={exam.id}>
                  <td>{exam.title}</td>
                  <td>{exam.class_name}</td>
                  <td className="num">{exam.scripts.ai_marked}</td>
                  <td className="num">{exam.scripts.waiting}</td>
                  <td className="num">{exam.scripts.confirmed}</td>
                  <td className="row-end">
                    <Link
                      className="button button-secondary button-small"
                      to={`/exams/${String(exam.id)}/queue`}
                      aria-label={t("markingQueue.openFor", { title: exam.title })}
                    >
                      {t("markingQueue.open")}
                      <Icon name="next" size={16} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
