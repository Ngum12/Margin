import { describe, expect, it } from "vitest";

import { nextSort, sortRows, zeroShares } from "./table";
import type { ResultRow } from "./table";

function row(code: string, marks: (number | null)[], confirmed = true): ResultRow {
  const total = confirmed ? marks.reduce<number>((s, m) => s + (m ?? 0), 0) : null;
  return {
    script_id: code.charCodeAt(0),
    student_code: code,
    student_name: null,
    status: confirmed ? "confirmed" : "ai_marked",
    confirmed,
    marks: confirmed ? marks : marks.map(() => null),
    total,
    percentage: total,
    test_model: false,
  };
}

const ROWS = [
  row("BBB", [2, 0]),
  row("AAA", [0, 0]),
  row("CCC", [1, 3]),
  row("DDD", [1, 1], false),
];

describe("results table", () => {
  it("sorts by a question with the unconfirmed script last", () => {
    const sorted = sortRows(ROWS, { key: 1, direction: "descending" });
    expect(sorted.map((r) => r.student_code)).toEqual(["CCC", "BBB", "AAA", "DDD"]);
  });

  it("sorts students by name or code", () => {
    const sorted = sortRows(ROWS, { key: "student", direction: "ascending" });
    expect(sorted.map((r) => r.student_code)).toEqual(["AAA", "BBB", "CCC", "DDD"]);
  });

  it("toggles the direction and starts marks with the highest", () => {
    expect(nextSort(null, "total")).toEqual({ key: "total", direction: "descending" });
    expect(nextSort({ key: "total", direction: "descending" }, "total").direction).toBe(
      "ascending",
    );
    expect(nextSort(null, "student").direction).toBe("ascending");
  });

  it("gives the share of confirmed scripts that scored zero on each question", () => {
    const questions = [
      { id: 1, label: "1", max_marks: 2, average: null },
      { id: 2, label: "2", max_marks: 3, average: null },
    ];
    expect(zeroShares({ questions, rows: ROWS })).toEqual([1 / 3, 2 / 3]);
    expect(zeroShares({ questions, rows: [ROWS[3] as ResultRow] })).toEqual([null, null]);
  });
});
