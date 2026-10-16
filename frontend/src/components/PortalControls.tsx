import { useState } from "react";
import { useTranslation } from "react-i18next";
import { request } from "../api/client";
import { useLoad } from "./useLoad";
import { ErrorMessage, Loading } from "./ui";

interface Policy {
  enabled: boolean;
  remark_days: number;
  remark_max: number;
  escalation: boolean;
  class_average: boolean;
  idle_minutes: number;
}
export function PortalSettings() {
  const { t } = useTranslation();
  const { state, reload } = useLoad(() => request<Policy>("GET", "/api/portal/settings"), []);
  const [error, setError] = useState<unknown>(null);
  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorMessage error={state.error} />;
  return (
    <section className="panel">
      <h2>{t("portal.settings")}</h2>
      <ErrorMessage error={error} />
      <form
        key={JSON.stringify(state.data)}
        onSubmit={(e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          void request("PUT", "/api/portal/settings", {
            json: {
              enabled: data.has("enabled"),
              escalation: data.has("escalation"),
              class_average: data.has("class_average"),
              remark_days: Number(data.get("remark_days")),
              remark_max: Number(data.get("remark_max")),
              idle_minutes: Number(data.get("idle_minutes")),
            },
          })
            .then(reload)
            .catch(setError);
        }}
      >
        {(["enabled", "escalation", "class_average"] as const).map((key) => (
          <label key={key}>
            <input type="checkbox" name={key} defaultChecked={state.data[key]} />
            {t(`portal.${key}`)}
          </label>
        ))}
        {(["remark_days", "remark_max", "idle_minutes"] as const).map((key) => (
          <label key={key}>
            {t(`portal.${key}`)}
            <input
              type="number"
              name={key}
              defaultValue={state.data[key]}
              min={key === "idle_minutes" ? 2 : 1}
              max={key === "remark_days" ? 90 : key === "remark_max" ? 20 : 30}
              required
            />
          </label>
        ))}
        <button>{t("common.save")}</button>
      </form>
    </section>
  );
}

interface Release {
  released: boolean;
  visibility: string;
  released_at: string | null;
}
export function ReleaseControls({ examId }: { examId: number }) {
  const { t } = useTranslation();
  const { state, reload } = useLoad(
    () => request<Release>("GET", `/api/exams/${String(examId)}/release`),
    [examId],
  );
  const [error, setError] = useState<unknown>(null);
  if (state.status !== "ready")
    return state.status === "error" ? <ErrorMessage error={state.error} /> : <Loading />;
  return (
    <section className="panel">
      <h2>{t("portal.releaseTitle")}</h2>
      <p>{t("portal.releaseHint")}</p>
      <ErrorMessage error={error} />
      <form
        key={JSON.stringify(state.data)}
        onSubmit={(e) => {
          e.preventDefault();
          const data = new FormData(e.currentTarget);
          void request("PUT", `/api/exams/${String(examId)}/release`, {
            json: { released: true, visibility: data.get("visibility") },
          })
            .then(reload)
            .catch(setError);
        }}
      >
        <label>
          {t("portal.visibility")}
          <select name="visibility" defaultValue={state.data.visibility}>
            {["marks", "notes", "scheme"].map((v) => (
              <option key={v} value={v}>
                {t(`portal.visibilityOptions.${v}`)}
              </option>
            ))}
          </select>
        </label>
        <button>{t(state.data.released ? "portal.updateRelease" : "portal.release")}</button>
        {state.data.released && (
          <button
            type="button"
            onClick={() => {
              void request("PUT", `/api/exams/${String(examId)}/release`, {
                json: { released: false, visibility: state.data.visibility },
              })
                .then(reload)
                .catch(setError);
            }}
          >
            {t("portal.unrelease")}
          </button>
        )}
      </form>
      {state.data.released_at && (
        <p>{t("portal.releasedAt", { date: new Date(state.data.released_at).toLocaleString() })}</p>
      )}
    </section>
  );
}
