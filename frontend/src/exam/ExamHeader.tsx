import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";

import { api } from "../api/endpoints";
import type { ExamSummary } from "../api/types";
import { useBreadcrumb } from "../components/breadcrumb";
import { Icon } from "../components/Icon";
import type { IconName } from "../components/icons";
import { StatusBadge } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { useSubjectName } from "./subjects";
import { workflowSteps } from "./workflow";
import type { StepState, WorkflowSteps } from "./workflow";

type HeaderExam = Pick<ExamSummary, "id" | "title" | "status"> &
  Partial<Pick<ExamSummary, "class_name" | "subject_code" | "exam_date" | "scripts">>;

const STEPS: { key: keyof WorkflowSteps; path: string }[] = [
  { key: "setup", path: "" },
  { key: "sheets", path: "/sheets" },
  { key: "scans", path: "/scans" },
  { key: "queue", path: "/queue" },
  { key: "results", path: "/results" },
];

const STATE_ICON: Record<StepState, IconName> = {
  done: "done",
  action: "alert",
  progress: "pending",
  later: "pending",
};

/** Exam title, its class and subject, and the tabs in the order of the work, each saying in
 * words whether it is done or needs action. */
export function ExamHeader({ exam }: { exam: HeaderExam }) {
  const { t } = useTranslation();
  const subjectName = useSubjectName();
  const base = `/exams/${String(exam.id)}`;
  // The summary (class, counts) and the cover sheets tell each tab's state.
  const known = exam.scripts !== undefined && exam.class_name !== undefined;
  const summary = useLoad(
    () => (known ? Promise.resolve(null) : api.exam(exam.id)),
    [exam.id, known, exam.status],
  );
  const sheets = useLoad(() => api.coverSheets(exam.id), [exam.id, exam.status]);
  const full = known ? exam : summary.state.status === "ready" ? summary.state.data : null;
  const className = exam.class_name ?? full?.class_name;
  useBreadcrumb([...(className ? [{ label: className }] : []), { label: exam.title, to: base }]);

  const steps = full?.scripts
    ? workflowSteps({
        status: exam.status,
        scripts: full.scripts,
        sheetsReady:
          sheets.state.status === "ready"
            ? sheets.state.data.length > 0 && sheets.state.data.every((r) => r.has_sheet)
            : null,
      })
    : null;
  const subject = exam.subject_code ?? full?.subject_code;
  const date = exam.exam_date ?? full?.exam_date;

  return (
    <header className="exam-header">
      <div className="exam-title-row">
        <div>
          <h1 className="exam-title">{exam.title}</h1>
          <p className="exam-meta">
            {[className, subject ? subjectName(subject) : null, date].filter(Boolean).join(" · ")}
          </p>
        </div>
        <StatusBadge status={exam.status} />
      </div>
      <nav className="exam-tabs" aria-label={t("examTabs.label")}>
        <ol>
          {STEPS.map(({ key, path }, index) => {
            const state = steps?.[key];
            return (
              <li key={key}>
                <NavLink to={`${base}${path}`} end>
                  <span className="exam-tab-name">
                    <span className="exam-tab-number" aria-hidden="true">
                      {index + 1}
                    </span>
                    {t(`examTabs.${key}`)}
                  </span>
                  {state && (
                    <span className={`exam-tab-state state-${state}`}>
                      <Icon name={STATE_ICON[state]} size={14} />
                      <span className="visually-hidden">, </span>
                      {t(`examTabs.state.${state}`)}
                    </span>
                  )}
                </NavLink>
              </li>
            );
          })}
        </ol>
      </nav>
    </header>
  );
}
