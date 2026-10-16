import { useEffect } from "react";
import { ScanInbox } from "../components/ScanInbox";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { api } from "../api/endpoints";
import type { ExamSummary } from "../api/types";
import { Icon } from "../components/Icon";
import { ErrorMessage, Loading, StatusBadge } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { useSubjectName } from "../exam/subjects";

function scriptCount(exam: ExamSummary): number {
  return exam.scripts.waiting + exam.scripts.ai_marked + exam.scripts.confirmed;
}

/** The teacher's day in the order of the work: scans to upload, scripts to review, scripts
 * confirmed. Real counts only, each linking to the work. */
export default function Home() {
  const { t, i18n } = useTranslation();
  const { state, reload } = useLoad(() => api.exams(), []);
  useEffect(() => {
    const timer = setInterval(reload, 5000);
    return () => {
      clearInterval(timer);
    };
  }, [reload]);
  const subjectName = useSubjectName();
  const today = new Intl.DateTimeFormat(i18n.language, {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date());

  return (
    <section className="dashboard">
      <ScanInbox />
      <header className="page-header">
        <div>
          <p className="eyebrow dashboard-date">{today}</p>
          <h1>{t("home.title")}</h1>
          <p className="page-lede">{t("studio.deskIntro")}</p>
        </div>
        <Link className="button" to="/exams/new">
          <Icon name="plus" />
          {t("home.newExam")}
        </Link>
      </header>
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorMessage error={state.error} />}
      {state.status === "ready" && (
        <>
          <WorkList exams={state.data} />
          <section className="panel exam-ledger" aria-labelledby="exams-heading">
            <div className="panel-header">
              <div>
                <p className="eyebrow">{t("studio.collection")}</p>
                <h2 id="exams-heading">{t("home.examsTitle")}</h2>
              </div>
              <span className="ledger-count">{String(state.data.length).padStart(2, "0")}</span>
            </div>
            {state.data.length === 0 ? (
              <p className="empty-state">{t("home.empty")}</p>
            ) : (
              <div
                className="table-wrap"
                role="region"
                aria-label={t("home.examsTitle")}
                tabIndex={0}
              >
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">{t("exam.title")}</th>
                      <th scope="col">{t("exam.class")}</th>
                      <th scope="col">{t("exam.subject")}</th>
                      <th scope="col">{t("exam.date")}</th>
                      <th scope="col">{t("exam.status")}</th>
                      <th scope="col" className="num">
                        {t("home.totalMarks")}
                      </th>
                      <th scope="col" className="num">
                        {t("home.waiting")}
                      </th>
                      <th scope="col" className="num">
                        {t("home.aiMarked")}
                      </th>
                      <th scope="col" className="num">
                        {t("home.confirmed")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.data.map((exam) => (
                      <tr key={exam.id}>
                        <td>
                          <Link className="strong-link" to={`/exams/${String(exam.id)}`}>
                            {exam.title}
                          </Link>
                        </td>
                        <td>{exam.class_name}</td>
                        <td>{subjectName(exam.subject_code)}</td>
                        <td className="nowrap">{exam.exam_date ?? "—"}</td>
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
        </>
      )}
    </section>
  );
}

function WorkList({ exams }: { exams: ExamSummary[] }) {
  const { t } = useTranslation();
  const needScans = exams.filter((e) => e.status !== "draft" && scriptCount(e) === 0);
  const toReview = exams.filter((e) => e.scripts.ai_marked > 0);
  const confirmed = exams.filter((e) => e.scripts.confirmed > 0);
  const reviewCount = toReview.reduce((sum, e) => sum + e.scripts.ai_marked, 0);
  const confirmedCount = confirmed.reduce((sum, e) => sum + e.scripts.confirmed, 0);

  return (
    <ol className="work-list" aria-label={t("home.workLabel")}>
      <WorkItem
        step={1}
        count={needScans.length}
        title={t("home.needScans", { count: needScans.length })}
        empty={t("home.needScansEmpty")}
        items={needScans.map((exam) => ({
          key: exam.id,
          to: `/exams/${String(exam.id)}/scans`,
          label: exam.title,
          detail: exam.class_name,
        }))}
      />
      <WorkItem
        step={2}
        count={reviewCount}
        title={t("home.toReview", { count: reviewCount })}
        empty={t("home.toReviewEmpty")}
        items={toReview.map((exam) => ({
          key: exam.id,
          to: `/exams/${String(exam.id)}/queue`,
          label: exam.title,
          detail: t("home.scriptsToReview", { count: exam.scripts.ai_marked }),
        }))}
      />
      <WorkItem
        step={3}
        count={confirmedCount}
        title={t("home.confirmedScripts", { count: confirmedCount })}
        empty={t("home.confirmedEmpty")}
        done
        items={confirmed.map((exam) => ({
          key: exam.id,
          to: `/exams/${String(exam.id)}/results`,
          label: exam.title,
          detail: t("home.confirmedOf", {
            confirmed: exam.scripts.confirmed,
            count: scriptCount(exam),
          }),
        }))}
      />
    </ol>
  );
}

function WorkItem({
  step,
  count,
  title,
  empty,
  items,
  done = false,
}: {
  step: number;
  count: number;
  title: string;
  empty: string;
  items: { key: number; to: string; label: string; detail: string }[];
  done?: boolean;
}) {
  return (
    <li className={count > 0 && !done ? "work-item work-item-active" : "work-item"}>
      <div className="work-step" aria-hidden="true">
        <span>0{step}</span>
        <Icon name={step === 1 ? "upload" : step === 2 ? "queue" : "check"} size={20} />
      </div>
      <div className="work-body">
        <p className="work-count">
          <span className="work-number">{count}</span> <span className="work-title">{title}</span>
        </p>
        {items.length === 0 ? (
          <p className="work-empty">{empty}</p>
        ) : (
          <ul className="work-links">
            {items.map((item) => (
              <li key={item.key}>
                <Link to={item.to}>
                  <span className="work-link-label">{item.label}</span>
                  <span className="work-link-detail">{item.detail}</span>
                  <Icon name="next" size={16} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}
