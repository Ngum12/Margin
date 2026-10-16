import { useTranslation } from "react-i18next";

import { RuleEditor, GroupEditor } from "./RuleEditor";
import type { Issue } from "../api/types";
import { issueMessage } from "../components/errors";
import { Icon } from "../components/Icon";
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

/** The mark scheme laid out like a printed one (question, points, marks on the right), with
 * every line editable where it stands. */
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
      <div className="scheme-sheet">
        {questions.length === 0 && <p className="empty-state scheme-empty">{t("editor.empty")}</p>}
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
                    className="in-place scheme-label"
                    value={question.label}
                    maxLength={40}
                    onChange={(e) => {
                      updateQuestion(qi, { label: e.target.value });
                    }}
                  />
                </Field>
                <Field label={t("editor.prompt")} hint={t("common.optional")}>
                  <textarea
                    className="in-place"
                    rows={2}
                    value={question.prompt_text}
                    onChange={(e) => {
                      updateQuestion(qi, { prompt_text: e.target.value });
                    }}
                  />
                </Field>
                <Field label={t("editor.maxMarks")}>
                  <input
                    className="input-short in-place scheme-marks"
                    inputMode="numeric"
                    value={question.max_marks}
                    onChange={(e) => {
                      updateQuestion(qi, { max_marks: e.target.value });
                    }}
                  />
                </Field>
              </div>

              <GroupEditor
                groups={question.groups ?? []}
                onChange={(groups) => {
                  updateQuestion(qi, { groups });
                }}
              />
              <table className="points">
                <thead>
                  <tr>
                    <th scope="col">{t("editor.pointDescription")}</th>
                    <th scope="col">{t("editor.alternatives")}</th>
                    <th scope="col" className="col-marks">
                      {t("editor.pointMarks")}
                    </th>
                    <th scope="col" className="col-tools">
                      <span className="visually-hidden">{t("common.actions")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {question.points.map((point, pi) => (
                    <tr key={point.key}>
                      <td>
                        <textarea
                          className="in-place"
                          rows={2}
                          aria-label={t("editor.pointDescription")}
                          value={point.description}
                          onChange={(e) => {
                            updatePoint(qi, pi, { description: e.target.value });
                          }}
                        />
                        <RuleEditor
                          rules={point.rules}
                          onChange={(rules) => {
                            updatePoint(qi, pi, { rules });
                          }}
                        />
                      </td>
                      <td>
                        <textarea
                          className="in-place"
                          rows={2}
                          aria-label={t("editor.alternatives")}
                          placeholder={t("editor.alternativesHint")}
                          value={point.alternatives}
                          onChange={(e) => {
                            updatePoint(qi, pi, { alternatives: e.target.value });
                          }}
                        />
                      </td>
                      <td className="col-marks">
                        <input
                          className="in-place scheme-marks"
                          inputMode="numeric"
                          aria-label={t("editor.pointMarks")}
                          value={point.marks}
                          onChange={(e) => {
                            updatePoint(qi, pi, { marks: e.target.value });
                          }}
                        />
                      </td>
                      <td className="col-tools">
                        <button
                          type="button"
                          className="button-quiet button-small"
                          onClick={() => {
                            updateQuestion(qi, {
                              points: question.points.filter((_, i) => i !== pi),
                            });
                          }}
                        >
                          <Icon name="trash" size={16} />
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
                  className="button-secondary button-small"
                  onClick={() => {
                    updateQuestion(qi, { points: [...question.points, emptyPoint()] });
                  }}
                >
                  <Icon name="plus" size={16} />
                  {t("editor.addPoint")}
                </button>
                <span className="points-total">
                  {t("editor.pointsTotal", {
                    total: pointsTotal,
                    max: parseWholeNumber(question.max_marks) ?? "?",
                  })}
                </span>
                <div className="question-tools">
                  <button
                    type="button"
                    className="button-quiet button-small icon-button"
                    disabled={qi === 0}
                    aria-label={t("editor.moveUp", { number: qi + 1 })}
                    title={t("editor.moveUp", { number: qi + 1 })}
                    onClick={() => {
                      onChange(move(questions, qi, qi - 1));
                    }}
                  >
                    <Icon name="sortUp" size={16} />
                  </button>
                  <button
                    type="button"
                    className="button-quiet button-small icon-button"
                    disabled={qi === questions.length - 1}
                    aria-label={t("editor.moveDown", { number: qi + 1 })}
                    title={t("editor.moveDown", { number: qi + 1 })}
                    onClick={() => {
                      onChange(move(questions, qi, qi + 1));
                    }}
                  >
                    <Icon name="sortDown" size={16} />
                  </button>
                  <button
                    type="button"
                    className="button-danger button-small"
                    onClick={() => {
                      onChange(questions.filter((_, i) => i !== qi));
                    }}
                  >
                    {t("editor.removeQuestion")}
                  </button>
                </div>
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
      </div>
      <div>
        <button
          type="button"
          className="button-secondary"
          onClick={() => {
            onChange([...questions, emptyQuestion(String(questions.length + 1))]);
          }}
        >
          <Icon name="plus" />
          {t("editor.addQuestion")}
        </button>
      </div>
    </div>
  );
}
