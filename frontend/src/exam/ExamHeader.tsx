import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";

import type { ExamSummary } from "../api/types";
import { StatusBadge } from "../components/ui";

/** Exam title, status and the tabs shared by the exam screens. */
export function ExamHeader({ exam }: { exam: Pick<ExamSummary, "id" | "title" | "status"> }) {
  const { t } = useTranslation();
  const base = `/exams/${String(exam.id)}`;
  return (
    <>
      <div className="section-header">
        <h1>{exam.title}</h1>
        <StatusBadge status={exam.status} />
      </div>
      <nav className="tabs" aria-label={t("examTabs.label")}>
        <NavLink to={base} end>
          {t("examTabs.setup")}
        </NavLink>
        <NavLink to={`${base}/sheets`}>{t("examTabs.sheets")}</NavLink>
        <NavLink to={`${base}/scans`}>{t("examTabs.scans")}</NavLink>
        <NavLink to={`${base}/queue`}>{t("examTabs.queue")}</NavLink>
      </nav>
    </>
  );
}
