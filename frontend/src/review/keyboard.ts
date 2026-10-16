// Keyboard shortcuts of the marking desk (review screen). Pure functions, unit-tested.

export type ReviewAction =
  | { type: "nextPoint" }
  | { type: "prevPoint" }
  | { type: "nextQuestion" }
  | { type: "prevQuestion" }
  | { type: "nextDeduction" }
  | { type: "setMarks"; marks: number }
  | { type: "accept" }
  | { type: "acceptAll" }
  | { type: "cycleCategory" }
  | { type: "focusComment" }
  | { type: "toggleEvidence" }
  | { type: "editTranscription" }
  | { type: "prevPage" }
  | { type: "nextPage" }
  | { type: "zoomIn" }
  | { type: "zoomOut" }
  | { type: "zoomFit" }
  | { type: "rotateRight" }
  | { type: "rotateLeft" }
  | { type: "nextScript" }
  | { type: "prevScript" }
  | { type: "confirm" }
  | { type: "help" };

export interface KeyLike {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
}

/** Shortcuts are ignored while the teacher is typing in a text field. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  if (target instanceof HTMLInputElement) {
    return !["button", "checkbox", "radio", "submit", "reset", "range"].includes(target.type);
  }
  return false;
}

/** Enter on a focused button, link or switch keeps its own meaning (press it), not "confirm". */
export function activatesOnEnter(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target instanceof HTMLButtonElement ||
    target instanceof HTMLAnchorElement ||
    target instanceof HTMLInputElement ||
    target.tagName === "SUMMARY"
  );
}

const SIMPLE: Record<string, ReviewAction> = {
  j: { type: "nextScript" },
  k: { type: "prevScript" },
  ArrowDown: { type: "nextPoint" },
  ArrowUp: { type: "prevPoint" },
  ArrowRight: { type: "nextQuestion" },
  ArrowLeft: { type: "prevQuestion" },
  d: { type: "nextDeduction" },
  a: { type: "accept" },
  A: { type: "acceptAll" },
  c: { type: "cycleCategory" },
  m: { type: "focusComment" },
  e: { type: "toggleEvidence" },
  t: { type: "editTranscription" },
  "[": { type: "prevPage" },
  "]": { type: "nextPage" },
  "+": { type: "zoomIn" },
  "=": { type: "zoomIn" },
  "-": { type: "zoomOut" },
  f: { type: "zoomFit" },
  r: { type: "rotateRight" },
  R: { type: "rotateLeft" },
  Enter: { type: "confirm" },
  "?": { type: "help" },
};

export function actionForKey(event: KeyLike): ReviewAction | null {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") return { type: "confirm" };
  // Leave the browser's and the system's own shortcuts alone.
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  if (/^[0-9]$/.test(event.key)) return { type: "setMarks", marks: Number(event.key) };
  if (event.shiftKey && event.key.startsWith("Arrow")) return null;
  return SIMPLE[event.key] ?? null;
}

/** For the help dialog (`?`): keys and the translation key of what they do. */
export const SHORTCUTS: readonly { keys: string[]; label: string }[] = [
  { keys: ["J", "K"], label: "review.keys.scripts" },
  { keys: ["←", "→"], label: "review.keys.questions" },
  { keys: ["↑", "↓"], label: "review.keys.points" },
  { keys: ["0–9"], label: "review.keys.marks" },
  { keys: ["E"], label: "review.keys.evidence" },
  { keys: ["Enter"], label: "review.keys.confirm" },
  { keys: ["D"], label: "review.keys.deduction" },
  { keys: ["A"], label: "review.keys.accept" },
  { keys: ["Shift+A"], label: "review.keys.acceptAll" },
  { keys: ["C"], label: "review.keys.category" },
  { keys: ["M"], label: "review.keys.comment" },
  { keys: ["T"], label: "review.keys.edit" },
  { keys: ["Esc"], label: "review.keys.escape" },
  { keys: ["[", "]"], label: "review.keys.pages" },
  { keys: ["+", "−", "F"], label: "review.keys.zoom" },
  { keys: ["R", "Shift+R"], label: "review.keys.rotate" },
  { keys: ["?"], label: "review.keys.help" },
];
