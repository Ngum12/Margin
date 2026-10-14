import { useState } from "react";
import type { SubmitEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router";

import { api } from "../../api/endpoints";
import type { Student } from "../../api/types";
import { ErrorMessage, Field, Loading } from "../../components/ui";
import { useLoad } from "../../components/useLoad";

export default function ClassStudents() {
  const { t } = useTranslation();
  const classId = Number(useParams().classId);
  const { state, reload } = useLoad(
    () => Promise.all([api.classes(), api.students(classId)]),
    [classId],
  );
  const [error, setError] = useState<unknown>(null);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorMessage error={state.error} />;
  const [classes, students] = state.data;
  const schoolClass = classes.find((c) => c.id === classId);

  return (
    <section>
      <p>
        <Link to="/admin/classes">← {t("classes.title")}</Link>
      </p>
      <h1>
        {schoolClass?.name ?? ""} <span className="muted">{schoolClass?.academic_year ?? ""}</span>
      </h1>
      <p className="muted">{t("students.privacyNote")}</p>
      <AddStudentsForm classId={classId} onAdded={reload} />
      <ErrorMessage error={error} />
      {students.length === 0 ? (
        <p className="card muted">{t("students.empty")}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("students.code")}</th>
                <th>{t("students.name")}</th>
                <th>{t("students.consent")}</th>
                <th>{t("students.consentRecorded")}</th>
              </tr>
            </thead>
            <tbody>
              {students.map((student) => (
                <StudentRow
                  key={student.id}
                  student={student}
                  onChange={(action) => {
                    setError(null);
                    action().then(reload).catch(setError);
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function StudentRow({
  student,
  onChange,
}: {
  student: Student;
  onChange: (action: () => Promise<unknown>) => void;
}) {
  const { t, i18n } = useTranslation();
  return (
    <tr>
      <td className="code">{student.code}</td>
      <td>{student.display_name ?? <span className="muted">—</span>}</td>
      <td>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={student.training_consent}
            onChange={(e) => {
              onChange(() => api.setConsent(student.id, e.target.checked));
            }}
          />
          <span>
            {student.training_consent ? t("students.consentYes") : t("students.consentNo")}
          </span>
        </label>
      </td>
      <td className="muted">
        {student.consent_recorded_at
          ? new Date(student.consent_recorded_at).toLocaleString(i18n.language)
          : "—"}
      </td>
    </tr>
  );
}

function AddStudentsForm({ classId, onAdded }: { classId: number; onAdded: () => void }) {
  const { t } = useTranslation();
  const [names, setNames] = useState("");
  const [count, setCount] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    setError(null);
    const listed = names
      .split("\n")
      .map((n) => n.trim())
      .filter((n) => n.length > 0);
    const blanks = Number.parseInt(count, 10);
    const entries =
      listed.length > 0 ? listed : Array<string>(Number.isNaN(blanks) ? 0 : blanks).fill("");
    if (entries.length === 0) return;
    try {
      await api.addStudents(classId, entries);
      setNames("");
      setCount("");
      onAdded();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <details className="card">
      <summary>{t("students.add")}</summary>
      <form className="form" onSubmit={(e) => void submit(e)}>
        <Field label={t("students.namesLabel")} hint={t("students.namesHint")}>
          <textarea
            rows={5}
            value={names}
            onChange={(e) => {
              setNames(e.target.value);
            }}
          />
        </Field>
        <Field label={t("students.countLabel")} hint={t("students.countHint")}>
          <input
            className="input-short"
            type="number"
            min={1}
            max={300}
            value={count}
            onChange={(e) => {
              setCount(e.target.value);
            }}
          />
        </Field>
        <ErrorMessage error={error} />
        <button type="submit">{t("students.create")}</button>
      </form>
    </details>
  );
}
