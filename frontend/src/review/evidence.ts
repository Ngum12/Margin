// Highlighting the AI's evidence inside a transcription. Pure function, unit-tested.

export interface Segment {
  text: string;
  mark: boolean;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Split `text` into plain and highlighted parts. Evidence matches ignoring letter case and
 * differences in spacing or line breaks (the same rule the server uses to check quotes). */
export function highlight(text: string, evidence: string): Segment[] {
  const words = evidence.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0 || text === "") return [{ text, mark: false }];
  const pattern = new RegExp(words.map(escapeRegExp).join("\\s+"), "gi");
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index;
    if (start > last) segments.push({ text: text.slice(last, start), mark: false });
    segments.push({ text: match[0], mark: true });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ text: text.slice(last), mark: false });
  return segments;
}

/** 1-based numbers of the lines of `text` that contain part of the evidence. */
export function evidenceLines(text: string, evidence: string): number[] {
  const lines = new Set<number>();
  let line = 1;
  for (const segment of highlight(text, evidence)) {
    const parts = segment.text.split("\n");
    if (segment.mark) {
      parts.forEach((part, index) => {
        if (part.trim()) lines.add(line + index);
      });
    }
    line += parts.length - 1;
  }
  return [...lines].sort((a, b) => a - b);
}

/** Line numbers as short ranges: [3, 4, 5, 8] → "3–5, 8". */
export function formatLines(lines: readonly number[]): string {
  const ranges: string[] = [];
  let start: number | null = null;
  let previous: number | null = null;
  for (const line of [...lines, Number.NaN]) {
    if (start !== null && previous !== null && line === previous + 1) {
      previous = line;
      continue;
    }
    if (start !== null && previous !== null) {
      ranges.push(start === previous ? String(start) : `${String(start)}–${String(previous)}`);
    }
    start = line;
    previous = line;
  }
  return ranges.join(", ");
}
