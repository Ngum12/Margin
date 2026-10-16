import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/endpoints";
import { request } from "../api/client";
import type { Student } from "../api/types";
import { useLoad } from "../components/useLoad";
import { ErrorMessage, Loading } from "../components/ui";

interface Row {
  name: string;
  code: string;
}
interface Draft {
  id: number;
  status: string;
  error: string | null;
  rows: Row[];
  model_name: string | null;
}
interface History {
  exam_id: number;
  title: string;
  term: string;
  subject: string;
  date: string;
  academic_year: string;
  total: number | null;
  maximum: number;
}
export default function Registers() {
  const { t } = useTranslation();
  const { state } = useLoad(() => api.classes(), []);
  const [id, setId] = useState<number | null>(null);
  return (
    <section>
      <h1>{t("register.title")}</h1>
      <label>
        {t("portal.class")}
        <select
          value={id ?? ""}
          onChange={(e) => {
            setId(Number(e.target.value));
          }}
        >
          <option value="">—</option>
          {state.status === "ready" &&
            state.data.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name} · {c.academic_year}
              </option>
            ))}
        </select>
      </label>
      {id && <Register key={id} classId={id} />}
    </section>
  );
}
function Register({ classId }: { classId: number }) {
  const { t } = useTranslation();
  const { state, reload } = useLoad(
    () =>
      Promise.all([
        api.students(classId),
        request<Draft[]>("GET", `/api/classes/${String(classId)}/imports`),
      ]),
    [classId],
  );
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [history, setHistory] = useState<History[] | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const timer = setInterval(reload, 5000);
    return () => {
      clearInterval(timer);
    };
  }, [reload]);
  async function upload(file: Blob, suffix: string) {
    setBusy(true);
    setError(null);
    try {
      await request(
        "POST",
        `/api/classes/${String(classId)}/imports?suffix=${encodeURIComponent(suffix)}`,
        { file },
      );
      reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  function move(student: Student, delta: number) {
    if (state.status !== "ready") return;
    const ids = state.data[0].filter((s) => s.is_active !== false).map((s) => s.id);
    const i = ids.indexOf(student.id);
    if (i + delta < 0 || i + delta >= ids.length) return;
    const current = ids[i];
    const other = ids[i + delta];
    if (current === undefined || other === undefined) return;
    [ids[i], ids[i + delta]] = [other, current];
    void request("PUT", `/api/classes/${String(classId)}/register-order`, {
      json: { student_ids: ids },
    })
      .then(reload)
      .catch(setError);
  }
  return (
    <>
      <div className="panel">
        <h2>{t("register.import")}</h2>
        <p>{t("register.help")}</p>
        <ErrorMessage error={error} />
        <label>
          {t("register.file")}
          <input
            type="file"
            accept=".xlsx,.csv,.txt,.pdf,image/jpeg,image/png,image/tiff"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void upload(f, `.${f.name.split(".").at(-1) ?? "txt"}`);
            }}
          />
        </label>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void upload(new Blob([text], { type: "text/plain" }), ".txt");
          }}
        >
          <label>
            {t("register.paste")}
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
              }}
              required
            />
          </label>
          <button disabled={busy}>{t("register.preview")}</button>
        </form>
      </div>
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorMessage error={state.error} />}
      {state.status === "ready" && (
        <>
          {state.data[1]
            .filter((d) => d.status !== "confirmed")
            .map((d) =>
              ["ready", "manual"].includes(d.status) ? (
                <Preview key={d.id} draft={d} students={state.data[0]} done={reload} />
              ) : (
                <p key={d.id}>
                  {t(`register.status.${d.status}`)}{" "}
                  {d.status === "failed" && (
                    <button
                      onClick={() => {
                        void request("POST", `/api/roster-imports/${String(d.id)}/retry`)
                          .then(reload)
                          .catch(setError);
                      }}
                    >
                      {t("register.retry")}
                    </button>
                  )}
                </p>
              ),
            )}
          <h2>{t("register.current")}</h2>
          <p>{t("register.orderHint")}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("portal.code")}</th>
                  <th>{t("students.name")}</th>
                  <th>{t("common.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {state.data[0].map((s) => (
                  <tr key={s.id} className={s.is_active === false ? "inactive" : undefined}>
                    <td>{s.code}</td>
                    <td>{s.display_name}</td>
                    <td>
                      <button
                        onClick={() => {
                          move(s, -1);
                        }}
                        disabled={s.is_active === false}
                        aria-label={t("register.up")}
                      >
                        ↑
                      </button>
                      <button
                        onClick={() => {
                          move(s, 1);
                        }}
                        disabled={s.is_active === false}
                        aria-label={t("register.down")}
                      >
                        ↓
                      </button>
                      <button
                        onClick={() => {
                          void request("PUT", `/api/students/${String(s.id)}/active`, {
                            json: { active: s.is_active === false },
                          })
                            .then(reload)
                            .catch(setError);
                        }}
                      >
                        {t(s.is_active === false ? "register.restore" : "register.remove")}
                      </button>
                      <button
                        onClick={() => {
                          void request<History[]>("GET", `/api/students/${String(s.id)}/history`)
                            .then(setHistory)
                            .catch(setError);
                        }}
                      >
                        {t("register.history")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {history && (
        <section className="panel">
          <h2>{t("register.history")}</h2>
          {history.length === 0 && <p>{t("register.noHistory")}</p>}
          <ol>
            {history.map((h) => (
              <li key={h.exam_id}>
                {h.academic_year} · {h.term} · {h.subject} · {h.date} · {h.title}: {h.total ?? "—"}/
                {h.maximum}
              </li>
            ))}
          </ol>
          <button
            onClick={() => {
              setHistory(null);
            }}
          >
            {t("common.close")}
          </button>
        </section>
      )}
    </>
  );
}
function Preview({
  draft,
  students,
  done,
}: {
  draft: Draft;
  students: Student[];
  done: () => void;
}) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Row[]>(
    draft.rows.length ? draft.rows : [{ name: "", code: "" }],
  );
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  function edit(i: number, key: keyof Row, value: string) {
    setRows(rows.map((r, j) => (i === j ? { ...r, [key]: value } : r)));
  }
  return (
    <section className="panel">
      <h2>{t("register.check")}</h2>
      <p>{t("register.reuse")}</p>
      <ErrorMessage error={error} />
      {draft.error && <p>{t(`errors.${draft.error}`)}</p>}
      <a href={`/api/roster-imports/${String(draft.id)}/original`} download>
        {t("register.original")}
      </a>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setBusy(true);
          void request("POST", `/api/roster-imports/${String(draft.id)}/confirm`, {
            json: { rows },
          })
            .then(done)
            .catch(setError)
            .finally(() => {
              setBusy(false);
            });
        }}
      >
        {rows.map((r, i) => (
          <div className="register-row" key={i}>
            <label>
              {t("students.name")}
              <input
                value={r.name}
                maxLength={200}
                onChange={(e) => {
                  edit(i, "name", e.target.value);
                }}
              />
            </label>
            <label>
              {t("portal.code")}
              <input
                value={r.code}
                maxLength={16}
                onChange={(e) => {
                  edit(i, "code", e.target.value);
                }}
              />
            </label>
            <button
              type="button"
              onClick={() => {
                setRows(rows.filter((_, j) => i !== j));
              }}
            >
              {t("common.remove")}
            </button>
            {!r.code &&
              students.some(
                (s) =>
                  s.display_name &&
                  s.display_name.toLocaleLowerCase() === r.name.toLocaleLowerCase(),
              ) && <p>{t("register.possibleDuplicate")}</p>}
          </div>
        ))}
        <button
          type="button"
          disabled={rows.length >= 300}
          onClick={() => {
            setRows([...rows, { name: "", code: "" }]);
          }}
        >
          {t("register.addRow")}
        </button>
        <button className="primary" disabled={busy || !rows.length}>
          {t("register.confirm")}
        </button>
      </form>
    </section>
  );
}
