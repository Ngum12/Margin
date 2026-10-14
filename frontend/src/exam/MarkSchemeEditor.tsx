import { useTranslation } from "react-i18next";

import type { Issue } from "../api/types";
import { issueMessage } from "../components/errors";
import { Field } from "../components/ui";
import { emptyPoint, emptyQuestion, issuesFor, parseWholeNumber } from "./markScheme";
import type { DraftPoint, DraftQuestion } from "./markScheme";

interface Props {
  questions: DraftQuestion[];
  issues: Issue[];
  onChange: (questions: DraftQuestion[]) => void;
}

function move<T>(items: T[], from: number, to: number): T[] {
  const copy = [...items];
  const [item] = copy.splice(from, 1);
  if (item !== undefined) copy.splice(to, 0, item);
  return copy;
}

export function MarkSchemeEditor({ questions, issues, onChange }: Props) {
  const { t } = useTranslation();

  function updateQuestion(index: number, patch: Partial<DraftQuestion>) {
    onChange(questions.map((q, i) => (i === index ? { ...q, ...patch } : q)));
  }

  function updatePoint(qi: number, pi: number, patch: Partial<DraftPoint>) {
    const question = questions[qi];
    if (!question) return;
    updateQuestion(qi, {
      points: question.points.map((p, i) => (i === pi ? { ...p, ...patch } : p)),
    });
  }

  return (
    <div className="editor">
      {questions.map((question, qi) => {
        const pointsTotal = question.points.reduce(
          (sum, p) => sum + (parseWholeNumber(p.marks) ?? 0),
          0,
        );
        const questionIssues = issuesFor(issues, qi);
        return (
          <fieldset key={question.key} className="question-card">
            <legend>{t("editor.questionHeading", { number: qi + 1 })}</legend>
            <div className="question-fields">
              <Field label={t("editor.label")}>
                <input
                  className="input-short"
                  value={question.label}
                  maxLength={40}
                  onChange={(e) => {
                    updateQuestion(qi, { label: e.target.value });
                  }}
                />
              </Field>
              <Field label={t("editor.maxMarks")}>
                <input
                  className="input-short"
                  inputMode="numeric"
                  value={question.max_marks}
                  onChange={(e) => {
                    updateQuestion(qi, { max_marks: e.target.value });
                  }}
                />
              </Field>
              <div className="question-tools">
                <button
                  type="button"
                  className="button-secondary"
                  disabled={qi === 0}
                  aria-label={t("editor.moveUp", { number: qi + 1 })}
                  onClick={() => {
                    onChange(move(questions, qi, qi - 1));
                  }}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="button-secondary"
                  disabled={qi === questions.length - 1}
                  aria-label={t("editor.moveDown", { number: qi + 1 })}
                  onClick={() => {
                    onChange(move(questions, qi, qi + 1));
                  }}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="button-danger"
                  onClick={() => {
                    onChange(questions.filter((_, i) => i !== qi));
                  }}
                >
                  {t("editor.removeQuestion")}
                </button>
              </div>
            </div>
            <Field label={t("editor.prompt")} hint={t("common.optional")}>
              <textarea
                rows={2}
                value={question.prompt_text}
                onChange={(e) => {
                  updateQuestion(qi, { prompt_text: e.target.value });
                }}
              />
            </Field>

            <table className="points">
              <thead>
                <tr>
                  <th>{t("editor.pointDescription")}</th>
                  <th className="num">{t("editor.pointMarks")}</th>
                  <th>{t("editor.alternatives")}</th>
                  <th>
                    <span className="visually-hidden">{t("common.actions")}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {question.points.map((point, pi) => (
                  <tr key={point.key}>
                    <td>
                      <textarea
                        rows={2}
                        aria-label={t("editor.pointDescription")}
                        value={point.description}
                        onChange={(e) => {
                          updatePoint(qi, pi, { description: e.target.value });
                        }}
                      />
                    </td>
                    <td className="num">
                      <input
                        className="input-short"
                        inputMode="numeric"
                        aria-label={t("editor.pointMarks")}
                        value={point.marks}
                        onChange={(e) => {
                          updatePoint(qi, pi, { marks: e.target.value });
                        }}
                      />
                    </td>
                    <td>
                      <textarea
                        rows={2}
                        aria-label={t("editor.alternatives")}
                        placeholder={t("editor.alternativesHint")}
                        value={point.alternatives}
                        onChange={(e) => {
                          updatePoint(qi, pi, { alternatives: e.target.value });
                        }}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className="button-secondary"
                        onClick={() => {
                          updateQuestion(qi, {
                            points: question.points.filter((_, i) => i !== pi),
                          });
                        }}
                      >
                        {t("editor.removePoint")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="question-footer">
              <button
                type="button"
                className="button-secondary"
                onClick={() => {
                  updateQuestion(qi, { points: [...question.points, emptyPoint()] });
                }}
              >
                {t("editor.addPoint")}
              </button>
              <span className="muted">
                {t("editor.pointsTotal", {
                  total: pointsTotal,
                  max: parseWholeNumber(question.max_marks) ?? "?",
                })}
              </span>
            </div>
            {questionIssues.length > 0 && (
              <ul className="inline-issues">
                {questionIssues.map((issue, i) => (
                  <li key={`${issue.code}-${String(i)}`}>{issueMessage(t, issue)}</li>
                ))}
              </ul>
            )}
          </fieldset>
        );
      })}
      <button
        type="button"
        className="button-secondary"
        onClick={() => {
          onChange([...questions, emptyQuestion(String(questions.length + 1))]);
        }}
      >
        {t("editor.addQuestion")}
      </button>
    </div>
  );
}
