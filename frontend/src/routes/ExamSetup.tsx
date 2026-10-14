import { useMemo, useState } from "react";
import type { SubmitEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router";

import { api } from "../api/endpoints";
import type { ExamDetail } from "../api/types";
import { ErrorMessage, Field, IssueList, Loading, StatusBadge } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { CsvImport } from "../exam/CsvImport";
import { MarkSchemeEditor } from "../exam/MarkSchemeEditor";
import { fromExam, fromScheme, toScheme, totalMarks, validateDraft } from "../exam/markScheme";
import type { DraftQuestion } from "../exam/markScheme";
import { subjectLabel } from "../exam/subjects";

export default function ExamSetup() {
  const { examId } = useParams();
  const id = Number(examId);
  const { state, set } = useLoad(() => api.exam(id), [id]);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorMessage error={state.error} />;
  return <ExamSetupLoaded key={state.data.id} exam={state.data} onSaved={set} />;
}

function ExamSetupLoaded({
  exam,
  onSaved,
}: {
  exam: ExamDetail;
  onSaved: (e: ExamDetail) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [questions, setQuestions] = useState<DraftQuestion[]>(() => fromExam(exam));
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const editable = exam.status === "draft";
  const report = useMemo(() => validateDraft(questions), [questions]);

  function edit(next: DraftQuestion[]) {
    setQuestions(next);
    setDirty(true);
    setMessage(null);
  }

  async function run(action: () => Promise<ExamDetail | undefined>, done?: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await action();
      if (updated) {
        onSaved(updated);
        setQuestions(fromExam(updated));
        setDirty(false);
      }
      if (done) setMessage(done);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="exam-setup">
      <div className="section-header">
        <h1>{exam.title}</h1>
        <StatusBadge status={exam.status} />
      </div>

      <ExamDetailsForm exam={exam} onSaved={onSaved} />

      <div className="section-header">
        <h2>{t("editor.title")}</h2>
        <span className="total">{t("editor.examTotal", { total: totalMarks(questions) })}</span>
      </div>

      {editable ? (
        <>
          <CsvImport
            onLoad={(scheme) => {
              edit(fromScheme(scheme));
            }}
          />
          <MarkSchemeEditor
            questions={questions}
            issues={[...report.blocking, ...report.readiness, ...report.notices]}
            onChange={edit}
          />
        </>
      ) : (
        <ReadOnlyScheme exam={exam} />
      )}

      <div className="card sticky-actions">
        <IssueList issues={report.blocking} tone="error" title={t("editor.mustFix")} />
        {editable && (
          <IssueList issues={report.readiness} tone="warning" title={t("editor.beforeReady")} />
        )}
        <IssueList issues={report.notices} tone="info" />
        <ErrorMessage error={error} />
        {message && (
          <p className="success" role="status">
            {message}
          </p>
        )}
        <div className="actions">
          {editable && (
            <button
              type="button"
              disabled={busy || !dirty || report.blocking.length > 0}
              onClick={() =>
                void run(() => api.saveMarkScheme(exam.id, toScheme(questions)), t("editor.saved"))
              }
            >
              {t("editor.save")}
            </button>
          )}
          {editable && (
            <button
              type="button"
              className="button-secondary"
              disabled={busy || dirty || report.blocking.length + report.readiness.length > 0}
              title={dirty ? t("editor.saveFirst") : undefined}
              onClick={() =>
                void run(() => api.setExamStatus(exam.id, "ready"), t("editor.nowReady"))
              }
            >
              {t("editor.markReady")}
            </button>
          )}
          {exam.status === "ready" && (
            <button
              type="button"
              className="button-secondary"
              disabled={busy}
              onClick={() => void run(() => api.setExamStatus(exam.id, "draft"))}
            >
              {t("editor.backToDraft")}
            </button>
          )}
          {editable && (
            <button
              type="button"
              className="button-danger"
              disabled={busy}
              onClick={() => {
                if (!window.confirm(t("editor.confirmDelete"))) return;
                void run(async () => {
                  await api.deleteExam(exam.id);
                  void navigate("/");
                  return undefined;
                });
              }}
            >
              {t("editor.deleteExam")}
            </button>
          )}
        </div>
        {dirty && <p className="muted">{t("editor.unsaved")}</p>}
      </div>
    </section>
  );
}

function ExamDetailsForm({
  exam,
  onSaved,
}: {
  exam: ExamDetail;
  onSaved: (e: ExamDetail) => void;
}) {
  const { t, i18n } = useTranslation();
  const subjects = useLoad(() => api.subjects(), []);
  const [title, setTitle] = useState(exam.title);
  const [subjectCode, setSubjectCode] = useState(exam.subject_code);
  const [examDate, setExamDate] = useState(exam.exam_date ?? "");
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const locked = exam.status !== "draft" && exam.status !== "ready";

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    setError(null);
    setSaved(false);
    try {
      onSaved(
        await api.updateExam(exam.id, {
          title,
          exam_date: examDate || null,
          ...(subjectCode !== exam.subject_code ? { subject_code: subjectCode } : {}),
        }),
      );
      setSaved(true);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="card form details-form" onSubmit={(e) => void submit(e)}>
      <div className="form-row">
        <Field label={t("exam.title")}>
          <input
            required
            maxLength={200}
            disabled={locked}
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              setSaved(false);
            }}
          />
        </Field>
        <Field label={t("exam.subject")}>
          <select
            value={subjectCode}
            disabled={exam.status !== "draft"}
            onChange={(e) => {
              setSubjectCode(e.target.value);
              setSaved(false);
            }}
          >
            {subjects.state.status === "ready" ? (
              subjects.state.data.map((s) => (
                <option key={s.code} value={s.code}>
                  {subjectLabel(s, i18n.language)}
                </option>
              ))
            ) : (
              <option value={subjectCode}>{subjectCode}</option>
            )}
          </select>
        </Field>
        <Field label={t("exam.date")}>
          <input
            type="date"
            disabled={locked}
            value={examDate}
            onChange={(e) => {
              setExamDate(e.target.value);
              setSaved(false);
            }}
          />
        </Field>
        <Field label={t("exam.class")}>
          <input value={exam.class_name} disabled />
        </Field>
      </div>
      <ErrorMessage error={error} />
      {!locked && (
        <div className="actions">
          <button type="submit" className="button-secondary">
            {t("exam.saveDetails")}
          </button>
          {saved && (
            <span className="success" role="status">
              {t("common.saved")}
            </span>
          )}
        </div>
      )}
    </form>
  );
}

function ReadOnlyScheme({ exam }: { exam: ExamDetail }) {
  const { t } = useTranslation();
  return (
    <div className="card">
      <p className="muted">{t("editor.lockedHelp")}</p>
      {exam.questions.map((q) => (
        <div key={q.id} className="readonly-question">
          <h3>
            {q.label}{" "}
            <span className="muted">({t("editor.marksCount", { count: q.max_marks })})</span>
          </h3>
          {q.prompt_text && <p>{q.prompt_text}</p>}
          <ul>
            {q.points.map((p) => (
              <li key={p.id}>
                {p.description}{" "}
                <span className="muted">({t("editor.marksCount", { count: p.marks })})</span>
                {p.alternatives.length > 0 && (
                  <span className="muted">
                    {" "}
                    · {t("editor.alsoAccept")}: {p.alternatives.join("; ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
