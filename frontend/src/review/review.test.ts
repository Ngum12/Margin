import { describe, expect, it } from "vitest";

import type { ReviewQuestion } from "../api/types";
import { evidenceLines, formatLines, highlight } from "./evidence";
import { flatPoints, minutesSeconds, nextDeduction, step } from "./focus";
import { actionForKey, activatesOnEnter, isTypingTarget } from "./keyboard";
import type { KeyLike } from "./keyboard";
import {
  FIT,
  isSideways,
  MAX_ZOOM,
  MIN_ZOOM,
  nextCategory,
  pan,
  rotate,
  transformFor,
  zoomIn,
  zoomOut,
} from "./viewer";

function key(k: string, mods: Partial<KeyLike> = {}): KeyLike {
  return { key: k, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...mods };
}

describe("keyboard map", () => {
  it("maps every documented shortcut", () => {
    expect(actionForKey(key("j"))).toEqual({ type: "nextScript" });
    expect(actionForKey(key("k"))).toEqual({ type: "prevScript" });
    expect(actionForKey(key("ArrowDown"))).toEqual({ type: "nextPoint" });
    expect(actionForKey(key("ArrowUp"))).toEqual({ type: "prevPoint" });
    expect(actionForKey(key("ArrowRight"))).toEqual({ type: "nextQuestion" });
    expect(actionForKey(key("ArrowLeft"))).toEqual({ type: "prevQuestion" });
    expect(actionForKey(key("e"))).toEqual({ type: "toggleEvidence" });
    expect(actionForKey(key("Enter"))).toEqual({ type: "confirm" });
    expect(actionForKey(key("d"))).toEqual({ type: "nextDeduction" });
    expect(actionForKey(key("0"))).toEqual({ type: "setMarks", marks: 0 });
    expect(actionForKey(key("7"))).toEqual({ type: "setMarks", marks: 7 });
    expect(actionForKey(key("a"))).toEqual({ type: "accept" });
    expect(actionForKey(key("A", { shiftKey: true }))).toEqual({ type: "acceptAll" });
    expect(actionForKey(key("c"))).toEqual({ type: "cycleCategory" });
    expect(actionForKey(key("m"))).toEqual({ type: "focusComment" });
    expect(actionForKey(key("t"))).toEqual({ type: "editTranscription" });
    expect(actionForKey(key("["))).toEqual({ type: "prevPage" });
    expect(actionForKey(key("]"))).toEqual({ type: "nextPage" });
    expect(actionForKey(key("+"))).toEqual({ type: "zoomIn" });
    expect(actionForKey(key("="))).toEqual({ type: "zoomIn" });
    expect(actionForKey(key("-"))).toEqual({ type: "zoomOut" });
    expect(actionForKey(key("f"))).toEqual({ type: "zoomFit" });
    expect(actionForKey(key("r"))).toEqual({ type: "rotateRight" });
    expect(actionForKey(key("R", { shiftKey: true }))).toEqual({ type: "rotateLeft" });
    expect(actionForKey(key("?", { shiftKey: true }))).toEqual({ type: "help" });
    expect(actionForKey(key("Enter", { ctrlKey: true }))).toEqual({ type: "confirm" });
    expect(actionForKey(key("Enter", { metaKey: true }))).toEqual({ type: "confirm" });
  });

  it("leaves browser shortcuts and other keys alone", () => {
    expect(actionForKey(key("ArrowDown", { shiftKey: true }))).toBeNull();
    expect(actionForKey(key("n"))).toBeNull();
    expect(actionForKey(key("r", { ctrlKey: true }))).toBeNull();
    expect(actionForKey(key("1", { altKey: true }))).toBeNull();
    expect(actionForKey(key("x"))).toBeNull();
    expect(actionForKey(key("Tab"))).toBeNull();
  });

  it("knows when the teacher is typing", () => {
    const text = document.createElement("input");
    const button = document.createElement("button");
    const radio = document.createElement("input");
    radio.type = "radio";
    expect(isTypingTarget(text)).toBe(true);
    expect(isTypingTarget(document.createElement("textarea"))).toBe(true);
    expect(isTypingTarget(document.createElement("select"))).toBe(true);
    expect(isTypingTarget(button)).toBe(false);
    expect(isTypingTarget(radio)).toBe(false);
    expect(isTypingTarget(document.body)).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });

  it("lets Enter press a focused button or link instead of confirming", () => {
    expect(activatesOnEnter(document.createElement("button"))).toBe(true);
    expect(activatesOnEnter(document.createElement("a"))).toBe(true);
    expect(activatesOnEnter(document.createElement("summary"))).toBe(true);
    expect(activatesOnEnter(document.createElement("li"))).toBe(false);
    expect(activatesOnEnter(document.body)).toBe(false);
  });
});

describe("page viewer state", () => {
  it("zooms within limits and re-centres at fit", () => {
    let view = FIT;
    for (let i = 0; i < 20; i += 1) view = zoomIn(view);
    expect(view.zoom).toBe(MAX_ZOOM);
    view = pan(view, 40, -10);
    expect(view).toMatchObject({ x: 40, y: -10 });
    for (let i = 0; i < 20; i += 1) view = zoomOut(view);
    expect(view).toEqual({ zoom: MIN_ZOOM, x: 0, y: 0 });
  });

  it("rotates in clockwise quarter turns", () => {
    expect(rotate(0, 90)).toBe(90);
    expect(rotate(270, 90)).toBe(0);
    expect(rotate(0, -90)).toBe(270);
    expect(isSideways(90)).toBe(true);
    expect(isSideways(180)).toBe(false);
    expect(transformFor({ zoom: 2, x: 5, y: 6 }, 180)).toBe(
      "translate(5px, 6px) scale(2) rotate(180deg)",
    );
  });

  it("cycles categories starting from the AI's", () => {
    expect(nextCategory(null, "omitted")).toBe("omitted");
    expect(nextCategory(null, null)).toBe("correct");
    expect(nextCategory("correct", "omitted")).toBe("conceptual_error");
    expect(nextCategory("omitted", null)).toBe("correct");
  });
});

describe("evidence highlight", () => {
  it("marks every match ignoring case and spacing", () => {
    expect(
      highlight("Metals conduct\nelectricity well. CONDUCT electricity", "conduct electricity"),
    ).toEqual([
      { text: "Metals ", mark: false },
      { text: "conduct\nelectricity", mark: true },
      { text: " well. ", mark: false },
      { text: "CONDUCT electricity", mark: true },
    ]);
  });

  it("treats evidence as text, not a pattern", () => {
    expect(highlight("x^2 (a+b)", "(a+b)")).toEqual([
      { text: "x^2 ", mark: false },
      { text: "(a+b)", mark: true },
    ]);
    expect(highlight("abc", "")).toEqual([{ text: "abc", mark: false }]);
    expect(highlight("abc", "zzz")).toEqual([{ text: "abc", mark: false }]);
  });
});

describe("point focus", () => {
  const questions = [
    {
      id: 1,
      points: [
        { id: 11, deducted: 0 },
        { id: 12, deducted: 1 },
      ],
    },
    {
      id: 2,
      points: [
        { id: 21, deducted: 0 },
        { id: 22, deducted: 2 },
      ],
    },
  ] as unknown as ReviewQuestion[];

  it("moves through points in order and stops at the ends", () => {
    const points = flatPoints(questions);
    expect(points.map((p) => p.point.id)).toEqual([11, 12, 21, 22]);
    expect(step(0, -1, 4)).toBe(0);
    expect(step(3, 1, 4)).toBe(3);
    expect(step(1, 1, 4)).toBe(2);
  });

  it("jumps to the next deduction, wrapping around", () => {
    const points = flatPoints(questions);
    expect(nextDeduction(points, 0)).toBe(1);
    expect(nextDeduction(points, 1)).toBe(3);
    expect(nextDeduction(points, 3)).toBe(1);
    expect(nextDeduction(flatPoints([questions[0]] as ReviewQuestion[]).slice(0, 1), 0)).toBeNull();
  });

  it("formats review time", () => {
    expect(minutesSeconds(754.4)).toEqual({ minutes: 12, seconds: 34 });
    expect(minutesSeconds(59.6)).toEqual({ minutes: 1, seconds: 0 });
  });
});

describe("evidence lines", () => {
  it("numbers the lines that hold the evidence", () => {
    const text = ["1(a) Metals conduct", "electricity well.", "1(b) Hydrogen"].join("\n");
    expect(evidenceLines(text, "conduct electricity")).toEqual([1, 2]);
    expect(evidenceLines(text, "hydrogen")).toEqual([3]);
    expect(evidenceLines(text, "")).toEqual([]);
  });

  it("writes line numbers as short ranges", () => {
    expect(formatLines([3, 4, 5, 8])).toBe("3–5, 8");
    expect(formatLines([2])).toBe("2");
    expect(formatLines([])).toBe("");
  });
});
