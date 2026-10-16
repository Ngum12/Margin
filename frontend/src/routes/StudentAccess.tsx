import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api/endpoints";
import { request } from "../api/client";
import { useLoad } from "../components/useLoad";
import { ErrorMessage, Loading } from "../components/ui";
import { Link } from "react-router";

export default function StudentAccess() {
  const { t } = useTranslation();
  const { state } = useLoad(() => api.classes(), []);
  const [selected, setSelected] = useState<number | null>(null);
  return (
    <section>
      <h1>{t("portal.access")}</h1>
      <p>{t("portal.slipsHint")}</p>
      <Link to="/student">{t("portal.openStudent")}</Link>
      {state.status === "error" && <ErrorMessage error={state.error} />}
      <label>
        {t("portal.class")}
        <select
          value={selected ?? ""}
          onChange={(e) => {
            setSelected(Number(e.target.value));
          }}
        >
          <option value="">—</option>
          {state.status === "ready" &&
            state.data.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name}
              </option>
            ))}
        </select>
      </label>
      {selected && <Roster key={selected} classId={selected} />}
    </section>
  );
}
function Roster({ classId }: { classId: number }) {
  const { t } = useTranslation();
  const { state } = useLoad(() => api.students(classId), [classId]);
  const [error, setError] = useState<unknown>(null);
  const [job, setJob] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [reset, setReset] = useState(false);
  function issue(ids: number[]) {
    setBusy(true);
    setError(null);
    void request<{ id: number }>("POST", "/api/portal/credentials", {
      json: { student_ids: ids, reset, key: crypto.randomUUID() },
    })
      .then((r) => {
        setJob(r.id);
      })
      .catch(setError)
      .finally(() => {
        setBusy(false);
      });
  }
  if (state.status !== "ready")
    return state.status === "error" ? <ErrorMessage error={state.error} /> : <Loading />;
  return (
    <div className="panel">
      <ErrorMessage error={error} />
      <label>
        <input
          type="checkbox"
          checked={reset}
          onChange={(e) => {
            setReset(e.target.checked);
          }}
        />
        {t("portal.resetPins")}
      </label>
      <button
        disabled={busy || !state.data.length}
        onClick={() => {
          issue(state.data.map((s) => s.id));
        }}
      >
        {t("portal.printSlips")}
      </button>
      {job && (
        <p>
          <Link to="/settings">{t("portal.printQueue")}</Link> ·{" "}
          <a href={`/api/portal/credentials/${String(job)}.pdf`} download>
            {t("portal.slipPdf")}
          </a>
        </p>
      )}
      <ul>
        {state.data.map((s) => (
          <li key={s.id}>
            {s.display_name ?? s.code} · {s.code}{" "}
            <button
              disabled={busy}
              onClick={() => {
                issue([s.id]);
              }}
            >
              {t("portal.issueSlip")}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
