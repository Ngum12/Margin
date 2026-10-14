import { useState } from "react";
import type { SubmitEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { api } from "../../api/endpoints";
import type { User } from "../../api/types";
import { ErrorMessage, Field, Loading } from "../../components/ui";
import { useLoad } from "../../components/useLoad";

export default function Classes() {
  const { t } = useTranslation();
  const { state, reload } = useLoad(() => Promise.all([api.classes(), api.users()]), []);
  const [error, setError] = useState<unknown>(null);

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorMessage error={state.error} />;
  const [classes, users] = state.data;
  const teachers = users.filter((u) => u.is_active);

  return (
    <section>
      <h1>{t("classes.title")}</h1>
      <NewClassForm teachers={teachers} onCreated={reload} />
      <ErrorMessage error={error} />
      {classes.length === 0 ? (
        <p className="card muted">{t("classes.empty")}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("classes.name")}</th>
                <th>{t("classes.year")}</th>
                <th>{t("classes.teacher")}</th>
                <th className="num">{t("classes.students")}</th>
              </tr>
            </thead>
            <tbody>
              {classes.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link to={`/admin/classes/${String(c.id)}`}>{c.name}</Link>
                  </td>
                  <td>{c.academic_year}</td>
                  <td>
                    <select
                      aria-label={t("classes.teacher")}
                      value={c.teacher_id}
                      onChange={(e) => {
                        setError(null);
                        api
                          .updateClass(c.id, { teacher_id: Number(e.target.value) })
                          .then(reload)
                          .catch(setError);
                      }}
                    >
                      {users.map((u) => (
                        <option key={u.id} value={u.id} disabled={!u.is_active}>
                          {u.display_name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="num">{c.student_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function defaultAcademicYear(): string {
  const now = new Date();
  // School years in Cameroon start in September.
  const start = now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1;
  return `${String(start)}/${String(start + 1)}`;
}

function NewClassForm({ teachers, onCreated }: { teachers: User[]; onCreated: () => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [year, setYear] = useState(defaultAcademicYear);
  const [teacherId, setTeacherId] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.createClass({ name, academic_year: year, teacher_id: Number(teacherId) });
      setName("");
      onCreated();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <details className="card">
      <summary>{t("classes.add")}</summary>
      <form className="form" onSubmit={(e) => void submit(e)}>
        <div className="form-row">
          <Field label={t("classes.name")}>
            <input
              required
              maxLength={100}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
              }}
            />
          </Field>
          <Field label={t("classes.year")}>
            <input
              required
              minLength={4}
              maxLength={20}
              value={year}
              onChange={(e) => {
                setYear(e.target.value);
              }}
            />
          </Field>
          <Field label={t("classes.teacher")}>
            <select
              required
              value={teacherId}
              onChange={(e) => {
                setTeacherId(e.target.value);
              }}
            >
              <option value="">{t("common.choose")}</option>
              {teachers.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <ErrorMessage error={error} />
        <button type="submit">{t("classes.create")}</button>
      </form>
    </details>
  );
}
