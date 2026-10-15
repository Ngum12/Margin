// Keyboard shortcuts of the script review screen (Phase 4 plan). Pure functions, unit-tested.

export type ReviewAction =
  | { type: "nextPoint" }
  | { type: "prevPoint" }
  | { type: "nextDeduction" }
  | { type: "setMarks"; marks: number }
  | { type: "accept" }
  | { type: "acceptAll" }
  | { type: "cycleCategory" }
  | { type: "focusComment" }
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

const SIMPLE: Record<string, ReviewAction> = {
  j: { type: "nextPoint" },
  k: { type: "prevPoint" },
  d: { type: "nextDeduction" },
  a: { type: "accept" },
  A: { type: "acceptAll" },
  c: { type: "cycleCategory" },
  m: { type: "focusComment" },
  e: { type: "editTranscription" },
  "[": { type: "prevPage" },
  "]": { type: "nextPage" },
  "+": { type: "zoomIn" },
  "=": { type: "zoomIn" },
  "-": { type: "zoomOut" },
  f: { type: "zoomFit" },
  r: { type: "rotateRight" },
  R: { type: "rotateLeft" },
  n: { type: "nextScript" },
  p: { type: "prevScript" },
  "?": { type: "help" },
};

export function actionForKey(event: KeyLike): ReviewAction | null {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") return { type: "confirm" };
  // Leave the browser's and the system's own shortcuts alone.
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  if (/^[0-9]$/.test(event.key)) return { type: "setMarks", marks: Number(event.key) };
  return SIMPLE[event.key] ?? null;
}

/** For the help dialog (`?`): keys and the translation key of what they do. */
export const SHORTCUTS: readonly { keys: string[]; label: string }[] = [
  { keys: ["j", "k"], label: "review.keys.points" },
  { keys: ["d"], label: "review.keys.deduction" },
  { keys: ["0–9"], label: "review.keys.marks" },
  { keys: ["a"], label: "review.keys.accept" },
  { keys: ["Shift+A"], label: "review.keys.acceptAll" },
  { keys: ["c"], label: "review.keys.category" },
  { keys: ["m"], label: "review.keys.comment" },
  { keys: ["e"], label: "review.keys.edit" },
  { keys: ["Esc"], label: "review.keys.escape" },
  { keys: ["[", "]"], label: "review.keys.pages" },
  { keys: ["+", "-", "f"], label: "review.keys.zoom" },
  { keys: ["r", "Shift+R"], label: "review.keys.rotate" },
  { keys: ["n", "p"], label: "review.keys.scripts" },
  { keys: ["Ctrl+Enter"], label: "review.keys.confirm" },
  { keys: ["?"], label: "review.keys.help" },
];
