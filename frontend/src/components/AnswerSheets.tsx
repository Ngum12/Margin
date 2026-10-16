import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { request } from "../api/client";
import { ErrorMessage } from "./ui";
import { PrintQueue } from "./SchoolHardware";

export function AnswerSheets({ examId }: { examId: number }) {
  const { t } = useTranslation();
  const [pages, setPages] = useState(2);
  useEffect(() => {
    let active = true;
    void request<{ pages_per_student: number }>("GET", `/api/exams/${String(examId)}/answer-sheets`)
      .then((data) => {
        if (active) setPages(data.pages_per_student);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [examId]);
  const [spares, setSpares] = useState(2);
  const [layout, setLayout] = useState("answer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<{ download_url: string; status: string } | null>(null);
  async function prepare(send: boolean) {
    setBusy(true);
    setError(null);
    try {
      setResult(
        await request("POST", `/api/exams/${String(examId)}/answer-sheets`, {
          json: {
            pages_per_student: pages,
            spares,
            layout,
            send_to_printer: send,
            request_key: crypto.randomUUID(),
          },
        }),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>{t("answerSheets.title")}</h2>
      <p>{t("answerSheets.help")}</p>
      <label>
        {t("answerSheets.layout")}
        <select
          value={layout}
          onChange={(e) => {
            setLayout(e.target.value);
          }}
        >
          <option value="answer">{t("answerSheets.answer")}</option>
          <option value="labels">{t("answerSheets.labels")}</option>
          <option value="cover">{t("answerSheets.cover")}</option>
        </select>
      </label>
      {layout !== "cover" && (
        <>
          <label>
            {t("answerSheets.pages")}
            <input
              type="number"
              min="1"
              max="20"
              value={pages}
              onChange={(e) => {
                setPages(Number(e.target.value));
              }}
            />
          </label>
          <label>
            {t("answerSheets.spares")}
            <input
              type="number"
              min="0"
              max="40"
              value={spares}
              onChange={(e) => {
                setSpares(Number(e.target.value));
              }}
            />
          </label>
        </>
      )}
      {layout === "labels" && <p>{t("answerSheets.labelHelp")}</p>}
      {layout === "cover" && <p>{t("answerSheets.coverHelp")}</p>}
      <div className="button-row">
        <button
          disabled={busy || pages < 1 || pages > 20 || spares < 0 || spares > 40}
          onClick={() => {
            void prepare(true);
          }}
        >
          {t("answerSheets.print")}
        </button>
        <button
          className="button-secondary"
          disabled={busy}
          onClick={() => {
            void prepare(false);
          }}
        >
          {t("answerSheets.pdf")}
        </button>
      </div>
      {error != null && <ErrorMessage error={error} />}
      {result && (
        <p role="status">
          {t(`hardware.status.${result.status}`)} ·{" "}
          <a href={result.download_url}>{t("answerSheets.download")}</a>
        </p>
      )}
      <PrintQueue examId={examId} />
    </section>
  );
}
