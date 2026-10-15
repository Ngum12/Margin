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
