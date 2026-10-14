import { describe, expect, it } from "vitest";

import type { DraftQuestion } from "./markScheme";
import {
  emptyQuestion,
  fromScheme,
  parseWholeNumber,
  toScheme,
  totalMarks,
  validateDraft,
} from "./markScheme";
import { at } from "../test/at";

function draft(): DraftQuestion[] {
  return fromScheme({
    questions: [
      {
        label: "1(a)",
        prompt_text: "State two properties of metals.",
        max_marks: 2,
        points: [
          {
            description: "Conducts electricity",
            marks: 1,
            alternatives: ["conductor", "good conductor"],
          },
          { description: "Malleable", marks: 1, alternatives: [] },
        ],
      },
      {
        label: "1(b)",
        prompt_text: "",
        max_marks: 1,
        points: [{ description: "Hydrogen", marks: 1, alternatives: [] }],
      },
    ],
  });
}

const codes = (issues: { code: string }[]) => issues.map((i) => i.code);

describe("validateDraft (mirrors backend rules)", () => {
  it("accepts a complete scheme", () => {
    const report = validateDraft(draft());
    expect(report.blocking).toEqual([]);
    expect(report.readiness).toEqual([]);
    expect(totalMarks(draft())).toBe(3);
  });

  it("needs at least one question to be ready", () => {
    expect(codes(validateDraft([]).readiness)).toEqual(["exam.no_questions"]);
  });

  it("blocks duplicate labels ignoring case and spaces", () => {
    const questions = draft();
    questions[1] = { ...at(questions, 1), label: " 1(A) " };
    const report = validateDraft(questions);
    expect(codes(report.blocking)).toEqual(["question.label_duplicate"]);
    expect(report.blocking[0]?.path).toEqual(["questions", 1, "label"]);
  });

  it("blocks empty labels", () => {
    expect(codes(validateDraft([emptyQuestion("")]).blocking)).toContain("question.label_required");
  });

  it.each(["0", "1.5", "abc", "", "101"])("blocks point marks %j", (marks) => {
    const questions = draft();
    at(questions, 1).points[0] = { ...at(at(questions, 1).points, 0), marks };
    expect(codes(validateDraft(questions).blocking)).toEqual(["point.marks_invalid"]);
  });

  it("warns when points cannot reach the maximum", () => {
    const questions = draft();
    questions[0] = { ...at(questions, 0), max_marks: "3" };
    const report = validateDraft(questions);
    expect(report.blocking).toEqual([]);
    expect(codes(report.readiness)).toEqual(["question.points_below_max"]);
    expect(report.readiness[0]?.params).toEqual({ label: "1(a)", points_total: 2, max_marks: 3 });
  });

  it("allows points above the maximum with a notice", () => {
    const questions = draft();
    questions[0] = { ...at(questions, 0), max_marks: "1" };
    const report = validateDraft(questions);
    expect(report.readiness).toEqual([]);
    expect(codes(report.notices)).toEqual(["question.points_exceed_max"]);
  });

  it("requires point descriptions to be ready", () => {
    const questions = draft();
    at(questions, 0).points[1] = { ...at(at(questions, 0).points, 1), description: "  " };
    expect(codes(validateDraft(questions).readiness)).toEqual(["point.description_required"]);
  });
});

describe("conversion", () => {
  it("round-trips through the API shape, trimming and splitting alternatives", () => {
    const questions = draft();
    questions[0] = { ...at(questions, 0), label: " 1(a) " };
    at(questions, 0).points[0] = {
      ...at(at(questions, 0).points, 0),
      alternatives: "conductor\n\n  good conductor \n",
    };

    const scheme = toScheme(questions);

    expect(scheme.questions[0]?.label).toBe("1(a)");
    expect(scheme.questions[0]?.points[0]?.alternatives).toEqual(["conductor", "good conductor"]);
    expect(scheme.questions[0]?.max_marks).toBe(2);
  });

  it("parses whole numbers only", () => {
    expect(parseWholeNumber(" 4 ")).toBe(4);
    expect(parseWholeNumber("4.0")).toBeNull();
    expect(parseWholeNumber("")).toBeNull();
  });
});
