import { describe, expect, it } from "vitest";

import tokens from "./tokens.css?raw";

// Every text/background pair the design uses, with the WCAG AA minimum it must meet: 4.5:1 for
// text, 3:1 for control borders and focus rings (docs/DESIGN.md lists the measured ratios).
const PAIRS: [foreground: string, background: string, minimum: number][] = [
  ["ink", "surface", 4.5],
  ["ink", "accent", 4.5],
  ["accent", "ink", 4.5],
  ["ink", "plum-soft", 4.5],
  ["rail-muted", "rail-active", 4.5],
  ["ink", "paper", 4.5],
  ["ink-2", "surface", 4.5],
  ["ink-2", "paper", 4.5],
  ["ink-3", "paper", 4.5],
  ["ink-3", "surface", 4.5],
  ["ink", "info-bg", 4.5],
  ["ink-2", "info-bg", 4.5],
  ["ink", "selected", 4.5],
  ["link", "surface", 4.5],
  ["link", "paper", 4.5],
  ["surface", "ink", 4.5],
  ["rail-text", "ink", 4.5],
  ["rail-muted", "ink", 4.5],
  ["rail-text", "rail-active", 4.5],
  ["mark-red", "surface", 4.5],
  ["mark-red", "paper", 4.5],
  ["confirmed", "surface", 4.5],
  ["confirmed", "confirmed-bg", 4.5],
  ["surface", "confirmed", 4.5],
  ["danger", "danger-bg", 4.5],
  ["danger", "surface", 4.5],
  ["warn", "warn-bg", 4.5],
  ["warn", "surface", 4.5],
  ["field-border", "surface", 3],
  ["field-border", "paper", 3],
  ["focus", "surface", 3],
  ["focus", "paper", 3],
  ["rail-focus", "ink", 3],
];

function token(name: string): string {
  const match = new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`).exec(tokens);
  if (!match?.[1]) throw new Error(`No colour token --${name}`);
  return match[1];
}

function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}

export function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

describe("design tokens", () => {
  it.each(PAIRS)("%s on %s meets %s:1", (foreground, background, minimum) => {
    expect(contrast(token(foreground), token(background))).toBeGreaterThanOrEqual(minimum);
  });

  it("keeps the marking red and the confirmed green distinct from the problem colours", () => {
    expect(token("mark-red")).not.toBe(token("danger"));
    expect(token("confirmed")).not.toBe(token("focus"));
  });
});
