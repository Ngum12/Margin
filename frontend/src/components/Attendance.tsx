import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { request } from "../api/client";
import { ErrorMessage } from "./ui";
import { useLoad } from "./useLoad";

interface Row {
  id: number;
  name: string;
  absent: boolean;
  received: boolean;
  missing_pages?: number[];
}

export function Attendance({ examId }: { examId: number }) {
  const { t } = useTranslation();
  const { state, reload } = useLoad(
    () => request<Row[]>("GET", `/api/exams/${String(examId)}/attendance`),
    [examId],
  );
  useEffect(() => {
    const timer = setInterval(reload, 5000);
    return () => {
      clearInterval(timer);
    };
  }, [reload]);
  const [error, setError] = useState<unknown>(null);
  if (state.status !== "ready") return null;
  return (
    <details className="panel">
      <summary>{t("hardware.attendance")}</summary>
      <ul>
        {state.data.map((row) => (
          <li key={row.id}>
            {row.name} ·{" "}
            {t(
              row.absent
                ? "hardware.absent"
                : row.received
                  ? "hardware.received"
                  : "hardware.awaiting",
            )}
            {row.missing_pages && row.missing_pages.length > 0 && (
              <span> · {t("answerSheets.missing", { pages: row.missing_pages.join(", ") })}</span>
            )}
            {!row.received && (
              <button
                className="button-secondary button-small"
                onClick={() => {
                  void request("PUT", `/api/exams/${String(examId)}/attendance/${String(row.id)}`, {
                    json: { absent: !row.absent },
                  })
                    .then(reload)
                    .catch(setError);
                }}
              >
                {t(row.absent ? "hardware.undoAbsence" : "hardware.markAbsent")}
              </button>
            )}
          </li>
        ))}
      </ul>
      {error != null && <ErrorMessage error={error} />}
    </details>
  );
}
