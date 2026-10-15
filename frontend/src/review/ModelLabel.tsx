import { useState } from "react";
import { useTranslation } from "react-i18next";

import { isTestModel } from "./testModel";

/** Which model made a transcription or a proposal: name · version · prompt version. Output from
 * a test model is labelled unmistakably (owner, 2026-10-15). */
export function ModelLabel({
  name,
  version,
  prompt,
}: {
  name: string | null;
  version: string | null;
  prompt?: string | null;
}) {
  const { t } = useTranslation();
  if (!name) return null;
  const parts = [name, version, prompt].filter(Boolean).join(" · ");
  return (
    <span className="model-label small">
      {isTestModel(name) && <span className="badge badge-test-model">{t("testModel.short")}</span>}{" "}
      <span className="muted">{t("testModel.model", { model: parts })}</span>
    </span>
  );
}

export function TestModelBadge() {
  const { t } = useTranslation();
  return <span className="badge badge-test-model">{t("testModel.short")}</span>;
}

/** Shown wherever test-model output appears. */
export function TestModelBanner({ count }: { count?: number }) {
  const { t } = useTranslation();
  return (
    <p className="notice notice-test-model" role="alert">
      <strong>{t("testModel.short")}</strong>{" "}
      {count === undefined ? t("testModel.script") : t("testModel.scripts", { count })}
    </p>
  );
}

/** A button that asks once more before running (re-running AI marking replaces what is shown). */
export function ConfirmButton({
  label,
  question,
  disabled,
  onConfirm,
}: {
  label: string;
  question: string;
  disabled?: boolean;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <button
        type="button"
        className="button-secondary"
        disabled={disabled}
        onClick={() => {
          setAsking(true);
        }}
      >
        {label}
      </button>
    );
  }
  return (
    <span className="confirm-inline" role="group" aria-label={label}>
      <span>{question}</span>{" "}
      <button
        type="button"
        onClick={() => {
          setAsking(false);
          onConfirm();
        }}
      >
        {t("common.yes")}
      </button>{" "}
      <button
        type="button"
        className="button-secondary"
        onClick={() => {
          setAsking(false);
        }}
      >
        {t("common.cancel")}
      </button>
    </span>
  );
}
