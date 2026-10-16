import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { request } from "../api/client";
import type { MarkSchemeInput } from "../api/types";
import { ErrorMessage, Field } from "../components/ui";
import { useLoad } from "../components/useLoad";

type Document = {
  id: number;
  kind: string;
  suffix: string;
  status: string;
  text: string;
  proposal: MarkSchemeInput | null;
  error: string | null;
};
type Entry = { id: number; title: string; subject_code: string };
export function DocumentImport({
  examId,
  editable,
  onLoad,
}: {
  examId: number;
  editable: boolean;
  onLoad: (scheme: MarkSchemeInput) => void;
}) {
  const { t } = useTranslation();
  const { state, reload } = useLoad(
    () => request<Document[]>("GET", `/api/exams/${String(examId)}/scheme-documents`),
    [examId],
  );
  const library = useLoad(() => request<Entry[]>("GET", "/api/scheme-library"), []);
  const [selected, setSelected] = useState<number | null>(null);
  const [kind, setKind] = useState("scheme");
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const timer = setInterval(reload, 5000);
    return () => {
      clearInterval(timer);
    };
  }, [reload]);
  const documents = state.status === "ready" ? state.data : [];
  const current = documents.find((d) => d.id === selected) ?? documents[0];
  async function upload(file: Blob, suffix: string) {
    setBusy(true);
    setError(null);
    try {
      const item = await request<Document>(
        "POST",
        `/api/exams/${String(examId)}/scheme-documents?suffix=${encodeURIComponent(suffix)}&kind=${kind}`,
        { file },
      );
      setSelected(item.id);
      reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }
  async function run(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err);
    }
  }
  return (
    <div className="panel document-import">
      <h3>{t("schemeImport.title")}</h3>
      <p className="muted">{t("schemeImport.help")}</p>
      {editable && (
        <>
          <Field label={t("schemeImport.kind")}>
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
              }}
            >
              <option value="scheme">{t("schemeImport.scheme")}</option>
              <option value="question_paper">{t("schemeImport.paper")}</option>
            </select>
          </Field>
          <Field label={t("schemeImport.file")}>
            <input
              type="file"
              disabled={busy}
              accept=".pdf,.docx,.jpg,.jpeg,.png,.tif,.tiff,.txt"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void upload(file, `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`);
              }}
            />
          </Field>
          <details>
            <summary>{t("schemeImport.paste")}</summary>
            <textarea
              aria-label={t("schemeImport.paste")}
              rows={8}
              value={text}
              maxLength={100000}
              onChange={(e) => {
                setText(e.target.value);
              }}
            />
            <button
              type="button"
              disabled={busy || !text.trim()}
              onClick={() => void upload(new Blob([text], { type: "text/plain" }), ".txt")}
            >
              {t("schemeImport.extract")}
            </button>
          </details>
        </>
      )}
      <ErrorMessage error={error} />
      {state.status === "error" && <ErrorMessage error={state.error} />}
      {documents.length > 0 && (
        <Field label={t("schemeImport.original")}>
          <select
            value={current?.id ?? ""}
            onChange={(e) => {
              setSelected(Number(e.target.value));
            }}
          >
            {documents.map((d) => (
              <option key={d.id} value={d.id}>
                {t(`schemeImport.${d.kind === "scheme" ? "scheme" : "paper"}`)} {d.id} ·{" "}
                {t(`schemeImport.status.${d.status}`)}
              </option>
            ))}
          </select>
        </Field>
      )}
      {current && (
        <>
          <a
            href={`/api/scheme-documents/${String(current.id)}/original`}
            target="_blank"
            rel="noreferrer"
          >
            {t("schemeImport.original")}
          </a>
          {[".png", ".jpg", ".jpeg"].includes(current.suffix) && (
            <img
              className="scheme-original"
              src={`/api/scheme-documents/${String(current.id)}/original`}
              alt={t("schemeImport.original")}
            />
          )}
          {current.suffix === ".pdf" && (
            <iframe
              className="scheme-original"
              title={t("schemeImport.original")}
              src={`/api/scheme-documents/${String(current.id)}/original`}
            />
          )}
          {current.text && (
            <details open={!current.proposal}>
              <summary>{t("schemeImport.text")}</summary>
              <pre className="scheme-text">{current.text}</pre>
            </details>
          )}
          {current.error && <p role="status">{t(`errors.${current.error}`)}</p>}
          {["manual", "failed"].includes(current.status) && (
            <button
              type="button"
              className="button-secondary"
              onClick={() =>
                void run(async () => {
                  await request("POST", `/api/scheme-documents/${String(current.id)}/retry`);
                  reload();
                })
              }
            >
              {t("common.retry")}
            </button>
          )}
          {editable && current.proposal && (
            <button
              type="button"
              onClick={() => {
                if (current.proposal) onLoad(current.proposal);
              }}
            >
              {t("schemeImport.use")}
            </button>
          )}
        </>
      )}
      <h3>{t("schemeImport.library")}</h3>
      {!editable && (
        <button
          type="button"
          className="button-secondary"
          onClick={() =>
            void run(async () => {
              await request("POST", "/api/scheme-library", { json: { exam_id: examId } });
              library.reload();
              setSaved(true);
            })
          }
        >
          {t("schemeImport.share")}
        </button>
      )}
      {saved && <p role="status">{t("common.saved")}</p>}
      {editable &&
        library.state.status === "ready" &&
        library.state.data.map((entry) => (
          <button
            type="button"
            className="button-quiet"
            key={entry.id}
            onClick={() =>
              void run(async () => {
                onLoad(
                  await request<MarkSchemeInput>("GET", `/api/scheme-library/${String(entry.id)}`),
                );
              })
            }
          >
            {entry.title} · {entry.subject_code}
          </button>
        ))}
    </div>
  );
}
