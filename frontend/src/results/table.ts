// Sorting the class results and the share of students who scored zero on each question.
// Pure functions, unit-tested.

import type { Results } from "../api/types";

export type ResultRow = Results["rows"][number];
export type SortKey = "student" | "total" | "percentage" | number; // a number is a question index
export interface Sort {
  key: SortKey;
  direction: "ascending" | "descending";
}

function value(row: ResultRow, key: SortKey): string | number | null {
  if (key === "student") return (row.student_name ?? row.student_code).toLocaleLowerCase();
  if (key === "total") return row.total;
  if (key === "percentage") return row.percentage;
  return row.marks[key] ?? null;
}

/** Rows in the chosen order; students without a mark (not confirmed) always come last. */
export function sortRows(rows: readonly ResultRow[], sort: Sort | null): ResultRow[] {
  if (!sort) return [...rows];
  const sign = sort.direction === "ascending" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = value(a, sort.key);
    const y = value(b, sort.key);
    if (x === null && y === null) return 0;
    if (x === null) return 1;
    if (y === null) return -1;
    if (typeof x === "string" && typeof y === "string") return sign * x.localeCompare(y);
    return sign * (Number(x) - Number(y));
  });
}

/** Clicking a column sorts it ascending, then descending. Marks start with the highest. */
export function nextSort(current: Sort | null, key: SortKey): Sort {
  if (current?.key === key) {
    return {
      key,
      direction: current.direction === "ascending" ? "descending" : "ascending",
    };
  }
  return { key, direction: key === "student" ? "ascending" : "descending" };
}

/** For each question, the share (0–1) of confirmed scripts that scored zero; null when no
 * script is confirmed yet. */
export function zeroShares(results: Pick<Results, "questions" | "rows">): (number | null)[] {
  const confirmed = results.rows.filter((r) => r.confirmed);
  return results.questions.map((_, index) => {
    const marks = confirmed.map((r) => r.marks[index]).filter((m) => m !== null && m !== undefined);
    if (marks.length === 0) return null;
    return marks.filter((m) => m === 0).length / marks.length;
  });
}

/** Questions where at least this share scored zero are worth reteaching. */
export const RETEACH_SHARE = 0.4;
