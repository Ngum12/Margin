import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/endpoints";
import type { ImportPreview, MarkSchemeInput } from "../api/types";
import { ErrorMessage, IssueList } from "../components/ui";

const MAX_FILE_BYTES = 1024 * 1024;

export function CsvImport({ onLoad }: { onLoad: (scheme: MarkSchemeInput) => void }) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tooLarge, setTooLarge] = useState(false);

  async function handleFile(file: File) {
    setPreview(null);
    setError(null);
    setTooLarge(file.size > MAX_FILE_BYTES);
    if (file.size > MAX_FILE_BYTES) return;
    try {
      setPreview(await api.previewImport(await file.text()));
    } catch (err) {
      setError(err);
    }
  }

  const scheme = preview?.scheme;
  return (
    <details className="card import">
      <summary>{t("import.title")}</summary>
      <p className="muted">{t("import.help")}</p>
      <pre className="example">
        question_label,question_prompt,question_max_marks,point_description,point_marks,point_alternatives
      </pre>
      <input
        type="file"
        accept=".csv,text/csv"
        aria-label={t("import.choose")}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleFile(file);
        }}
      />
      {tooLarge && (
        <p className="error" role="alert">
          {t("issues.import.too_large", { max_kb: MAX_FILE_BYTES / 1024 })}
        </p>
      )}
      <ErrorMessage error={error} />
      {preview && <IssueList issues={preview.issues} tone="error" title={t("import.problems")} />}
      {scheme && (
        <div className="import-result">
          <p>
            {t("import.summary", {
              questions: scheme.questions.length,
              marks: scheme.questions.reduce((s, q) => s + q.max_marks, 0),
            })}
          </p>
          {preview.validation && <IssueList issues={preview.validation.readiness} tone="warning" />}
          <button
            type="button"
            onClick={() => {
              onLoad(scheme);
              setPreview(null);
            }}
          >
            {t("import.load")}
          </button>
          <p className="muted">{t("import.replaceWarning")}</p>
        </div>
      )}
    </details>
  );
}
