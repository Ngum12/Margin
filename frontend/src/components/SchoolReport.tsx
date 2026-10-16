import { useState } from "react";
import { useTranslation } from "react-i18next";
import { request } from "../api/client";
import { useLoad } from "./useLoad";
import { ErrorMessage } from "./ui";

export function SchoolReport({ examId }: { examId: number }) {
  const { t } = useTranslation();
  const { state, reload } = useLoad(
    () =>
      request<{ term: string; academic_year: string }>("GET", `/api/exams/${String(examId)}/term`),
    [examId],
  );
  const [error, setError] = useState<unknown>(null);
  return (
    <div className="panel">
      <h2>{t("register.report")}</h2>
      <a href={`/api/exams/${String(examId)}/results.xlsx`} download>
        {t("register.excel")}
      </a>
      <ErrorMessage error={error} />
      {state.status === "ready" && (
        <form
          key={state.data.term}
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            void request("PUT", `/api/exams/${String(examId)}/term`, {
              json: { term: form.get("term") },
            })
              .then(reload)
              .catch(setError);
          }}
        >
          <label>
            {t("register.term")}
            <input name="term" defaultValue={state.data.term} maxLength={200} />
          </label>
          <p>{state.data.academic_year}</p>
          <button>{t("common.save")}</button>
        </form>
      )}
    </div>
  );
}
