import { useState } from "react";
import type { SubmitEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { api } from "../api/endpoints";
import { ErrorMessage, Field, Loading } from "../components/ui";
import { useLoad } from "../components/useLoad";
import { subjectLabel } from "../exam/subjects";

export default function NewExam() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { state } = useLoad(() => Promise.all([api.classes(), api.subjects()]), []);
  const [classId, setClassId] = useState("");
  const [subjectCode, setSubjectCode] = useState("");
  const [title, setTitle] = useState("");
  const [examDate, setExamDate] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorMessage error={state.error} />;
  const [classes, subjects] = state.data;

  if (classes.length === 0) {
    return (
      <section className="card">
        <h1>{t("newExam.title")}</h1>
        <p>{t("newExam.noClasses")}</p>
      </section>
    );
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const exam = await api.createExam({
        class_id: Number(classId),
        subject_code: subjectCode,
        title,
        exam_date: examDate || null,
      });
      void navigate(`/exams/${String(exam.id)}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <section className="card narrow">
      <h1>{t("newExam.title")}</h1>
      <form className="form" onSubmit={(e) => void submit(e)}>
        <Field label={t("exam.class")}>
          <select
            required
            value={classId}
            onChange={(e) => {
              setClassId(e.target.value);
            }}
          >
            <option value="">{t("common.choose")}</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.academic_year})
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("exam.subject")}>
          <select
            required
            value={subjectCode}
            onChange={(e) => {
              setSubjectCode(e.target.value);
            }}
          >
            <option value="">{t("common.choose")}</option>
            {subjects.map((s) => (
              <option key={s.code} value={s.code}>
                {subjectLabel(s, i18n.language)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("exam.title")}>
          <input
            required
            maxLength={200}
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
            }}
          />
        </Field>
        <Field label={t("exam.date")} hint={t("common.optional")}>
          <input
            type="date"
            value={examDate}
            onChange={(e) => {
              setExamDate(e.target.value);
            }}
          />
        </Field>
        <ErrorMessage error={error} />
        <button type="submit" disabled={busy}>
          {t("newExam.create")}
        </button>
      </form>
    </section>
  );
}
