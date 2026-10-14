// Mark scheme editor model. Validation mirrors backend/app/services/mark_scheme.py and uses the
// same issue codes, so teachers see problems while typing. The server remains authoritative.

import type { ExamDetail, Issue, MarkSchemeInput } from "../api/types";

export const MAX_LABEL_LENGTH = 20;
export const MAX_MARKS_PER_ITEM = 100;
export const MAX_QUESTIONS = 100;
export const MAX_POINTS_PER_QUESTION = 50;

export interface DraftPoint {
  key: string;
  description: string;
  marks: string; // as typed; whole marks only (D-018)
  alternatives: string; // one per line
}

export interface DraftQuestion {
  key: string;
  label: string;
  prompt_text: string;
  max_marks: string;
  points: DraftPoint[];
}

export interface Report {
  blocking: Issue[];
  readiness: Issue[];
  notices: Issue[];
}

let nextKey = 0;
export function newKey(): string {
  nextKey += 1;
  return `k${String(nextKey)}`;
}

export function emptyPoint(): DraftPoint {
  return { key: newKey(), description: "", marks: "1", alternatives: "" };
}

export function emptyQuestion(label = ""): DraftQuestion {
  return { key: newKey(), label, prompt_text: "", max_marks: "1", points: [emptyPoint()] };
}

/** Whole number from user input, or null if it is not one. */
export function parseWholeNumber(value: string): number | null {
  const trimmed = value.trim();
  return /^-?\d+$/.test(trimmed) ? Number(trimmed) : null;
}

function splitAlternatives(text: string): string[] {
  return text
    .split("\n")
    .map((a) => a.trim())
    .filter((a) => a.length > 0);
}

export function fromScheme(scheme: MarkSchemeInput): DraftQuestion[] {
  return scheme.questions.map((q) => ({
    key: newKey(),
    label: q.label,
    prompt_text: q.prompt_text,
    max_marks: String(q.max_marks),
    points: q.points.map((p) => ({
      key: newKey(),
      description: p.description,
      marks: String(p.marks),
      alternatives: p.alternatives.join("\n"),
    })),
  }));
}

export function fromExam(exam: ExamDetail): DraftQuestion[] {
  return fromScheme({ questions: exam.questions });
}

/** Convert to the API shape. Only call when validateDraft reports no blocking issues. */
export function toScheme(questions: DraftQuestion[]): MarkSchemeInput {
  return {
    questions: questions.map((q) => ({
      label: q.label.trim(),
      prompt_text: q.prompt_text.trim(),
      max_marks: parseWholeNumber(q.max_marks) ?? 0,
      points: q.points.map((p) => ({
        description: p.description.trim(),
        marks: parseWholeNumber(p.marks) ?? 0,
        alternatives: splitAlternatives(p.alternatives),
      })),
    })),
  };
}

export function totalMarks(questions: DraftQuestion[]): number {
  return questions.reduce((sum, q) => sum + (parseWholeNumber(q.max_marks) ?? 0), 0);
}

function inRange(value: number | null): value is number {
  return value !== null && value >= 1 && value <= MAX_MARKS_PER_ITEM;
}

export function validateDraft(questions: DraftQuestion[]): Report {
  const report: Report = { blocking: [], readiness: [], notices: [] };
  if (questions.length === 0)
    report.readiness.push({ code: "exam.no_questions", path: [], params: {} });
  if (questions.length > MAX_QUESTIONS) {
    report.blocking.push({
      code: "exam.too_many_questions",
      path: [],
      params: { max: MAX_QUESTIONS },
    });
  }

  const seen = new Map<string, number>();
  questions.forEach((question, qi) => {
    const qpath = ["questions", qi];
    const label = question.label.trim();
    const key = label.toLocaleLowerCase();
    const maxMarks = parseWholeNumber(question.max_marks);

    if (!label) {
      report.blocking.push({
        code: "question.label_required",
        path: [...qpath, "label"],
        params: {},
      });
    } else if (label.length > MAX_LABEL_LENGTH) {
      report.blocking.push({
        code: "question.label_too_long",
        path: [...qpath, "label"],
        params: { max: MAX_LABEL_LENGTH },
      });
    } else if (seen.has(key)) {
      report.blocking.push({
        code: "question.label_duplicate",
        path: [...qpath, "label"],
        params: { label, first: (seen.get(key) ?? 0) + 1 },
      });
    } else {
      seen.set(key, qi);
    }

    if (!inRange(maxMarks)) {
      report.blocking.push({
        code: "question.max_marks_invalid",
        path: [...qpath, "max_marks"],
        params: { max: MAX_MARKS_PER_ITEM, label },
      });
    }
    if (question.points.length > MAX_POINTS_PER_QUESTION) {
      report.blocking.push({
        code: "question.too_many_points",
        path: qpath,
        params: { max: MAX_POINTS_PER_QUESTION },
      });
    }
    if (question.points.length === 0) {
      report.readiness.push({ code: "question.no_points", path: qpath, params: { label } });
    }

    let pointsValid = true;
    for (const [pi, point] of question.points.entries()) {
      const ppath = [...qpath, "points", pi];
      if (!inRange(parseWholeNumber(point.marks))) {
        pointsValid = false;
        report.blocking.push({
          code: "point.marks_invalid",
          path: [...ppath, "marks"],
          params: { max: MAX_MARKS_PER_ITEM, label },
        });
      }
      if (!point.description.trim()) {
        report.readiness.push({
          code: "point.description_required",
          path: [...ppath, "description"],
          params: { label },
        });
      }
    }

    if (question.points.length > 0 && pointsValid && inRange(maxMarks)) {
      const pointsTotal = question.points.reduce((s, p) => s + (parseWholeNumber(p.marks) ?? 0), 0);
      const params = { label, points_total: pointsTotal, max_marks: maxMarks };
      if (pointsTotal < maxMarks)
        report.readiness.push({ code: "question.points_below_max", path: qpath, params });
      else if (pointsTotal > maxMarks)
        report.notices.push({ code: "question.points_exceed_max", path: qpath, params });
    }
  });
  return report;
}

/** Issues that point at a given question (for showing them inline). */
export function issuesFor(issues: Issue[], questionIndex: number): Issue[] {
  return issues.filter((i) => i.path[0] === "questions" && i.path[1] === questionIndex);
}
