import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Icon } from "./Icon";

function motionQuery() {
  if (typeof window.matchMedia !== "function") return null;
  return window.matchMedia("(prefers-reduced-motion: reduce)");
}

const STAGES = ["scan", "read", "propose", "review"] as const;

/** An illustrative, controllable product story. Never displays actual student data. */
export function MarkingPreview() {
  const { t } = useTranslation();
  const [step, setStep] = useState(0);
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(() => motionQuery()?.matches ?? false);

  useEffect(() => {
    const query = motionQuery();
    if (!query) return;
    const changed = (event: MediaQueryListEvent) => {
      setReduced(event.matches);
    };
    query.addEventListener("change", changed);
    return () => {
      query.removeEventListener("change", changed);
    };
  }, []);

  useEffect(() => {
    if (paused || reduced) return;
    const timer = window.setInterval(() => {
      setStep((current) => (current + 1) % STAGES.length);
    }, 4200);
    return () => {
      window.clearInterval(timer);
    };
  }, [paused, reduced]);

  const stage = STAGES[step] ?? "scan";
  return (
    <figure className="marking-preview" data-step={step} data-paused={paused || reduced}>
      <div className="preview-scene" aria-hidden="true">
        <div className="orbit orbit-one" />
        <div className="orbit orbit-two" />
        <div className="preview-sheet sheet-behind" />
        <div className="preview-sheet sheet-main">
          <div className="sample-top">
            <span>{t("studio.sampleSubject")}</span>
            <span>01 / 03</span>
          </div>
          <div className="sample-id">{t("studio.sampleCode")}</div>
          <h3>{t("studio.sampleQuestion")}</h3>
          <div className="sample-handwriting">
            <span className="sample-answer">{t("studio.sampleAnswer1")}</span>
            <span className="sample-answer">{t("studio.sampleAnswer2")}</span>
            <span className="sample-answer last-answer">{t("studio.sampleAnswer3")}</span>
          </div>
          <div className="sample-scan-line" />
          <span className="sample-tick tick-one">✓</span>
          <span className="sample-tick tick-two">✓</span>
          <div className="sample-score">
            2<span>/2</span>
            <svg viewBox="0 0 100 70">
              <ellipse cx="50" cy="35" rx="43" ry="27" />
            </svg>
          </div>
          <span className="sample-note">{t("studio.sampleNote")}</span>
          <div className="sample-bottom">
            <span>margin.</span>
            <span>{t("studio.samplePaper")}</span>
          </div>
        </div>
        <div className="reading-tag">
          <span className="preview-pulse" />
          <span>{t(`studio.${stage}Tag`)}</span>
        </div>
        <div className="evidence-note">
          <span className="evidence-note-icon">
            <Icon name={step === 3 ? "check" : "exams"} size={18} />
          </span>
          <div>
            <span className="eyebrow">{t("studio.teacherControl")}</span>
            <strong>{t(`studio.${stage}Detail`)}</strong>
          </div>
        </div>
      </div>
      <figcaption className="preview-caption">
        <div className="preview-caption-top">
          <span>{t("studio.illustration")}</span>
          {!reduced && (
            <button
              type="button"
              className="preview-pause"
              onClick={() => {
                setPaused(!paused);
              }}
            >
              {t(paused ? "studio.play" : "studio.pause")}
            </button>
          )}
        </div>
        <div className="preview-steps" role="group" aria-label={t("studio.previewLabel")}>
          {STAGES.map((name, index) => (
            <button
              type="button"
              key={name}
              aria-pressed={step === index}
              onClick={() => {
                setStep(index);
                setPaused(true);
              }}
            >
              <span className="preview-step-track">
                <span />
              </span>
              <span className="preview-step-label">
                <span>0{index + 1}</span>
                {t(`studio.${name}`)}
              </span>
            </button>
          ))}
        </div>
      </figcaption>
    </figure>
  );
}
