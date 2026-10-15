// Moving the focus between mark scheme points, and time formatting. Pure functions, unit-tested.

import type { ReviewPoint, ReviewQuestion } from "../api/types";

export interface FlatPoint {
  point: ReviewPoint;
  question: ReviewQuestion;
}

export function flatPoints(questions: readonly ReviewQuestion[]): FlatPoint[] {
  return questions.flatMap((question) => question.points.map((point) => ({ point, question })));
}

export function step(index: number, delta: 1 | -1, count: number): number {
  if (count === 0) return 0;
  return Math.min(count - 1, Math.max(0, index + delta));
}

/** Index of the next point after `index` (wrapping) where the AI deducted marks, or null. */
export function nextDeduction(points: readonly FlatPoint[], index: number): number | null {
  for (let offset = 1; offset <= points.length; offset += 1) {
    const candidate = (index + offset) % points.length;
    if ((points[candidate]?.point.deducted ?? 0) > 0) return candidate;
  }
  return null;
}

/** Whole minutes and seconds for a review time. */
export function minutesSeconds(total: number): { minutes: number; seconds: number } {
  const rounded = Math.round(total);
  return { minutes: Math.floor(rounded / 60), seconds: rounded % 60 };
}
