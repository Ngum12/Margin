// Zoom, pan and rotation of the page viewer, and the category cycle. Pure functions, unit-tested.

import type { ErrorCategory, Rotation } from "../api/types";
import { ERROR_CATEGORIES } from "../api/types";

export interface ViewState {
  zoom: number;
  x: number;
  y: number;
}

export const FIT: ViewState = { zoom: 1, x: 0, y: 0 };
export const MIN_ZOOM = 0.5;
export const MAX_ZOOM = 5;
const STEP = 1.25;

function clampZoom(zoom: number): number {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(zoom * 1000) / 1000));
}

export function zoomIn(view: ViewState): ViewState {
  return { ...view, zoom: clampZoom(view.zoom * STEP) };
}

export function zoomOut(view: ViewState): ViewState {
  const zoom = clampZoom(view.zoom / STEP);
  // Back at (or below) fit, re-centre so the page cannot be lost off screen.
  return zoom <= 1 ? { zoom, x: 0, y: 0 } : { ...view, zoom };
}

export function pan(view: ViewState, dx: number, dy: number): ViewState {
  return { ...view, x: view.x + dx, y: view.y + dy };
}

/** Clockwise quarter turns: `rotate(270, 90)` is 0. */
export function rotate(rotation: number, delta: 90 | -90): Rotation {
  return ((((rotation + delta) % 360) + 360) % 360) as Rotation;
}

/** CSS transform for the page image (rotation is clockwise degrees, like CSS). */
export function transformFor(view: ViewState, rotation: number): string {
  return `translate(${String(view.x)}px, ${String(view.y)}px) scale(${String(view.zoom)}) rotate(${String(rotation)}deg)`;
}

/** A quarter-turned page is laid out with its sides swapped. */
export function isSideways(rotation: number): boolean {
  return rotation % 180 !== 0;
}

/** The category the `c` key moves to: from none, the AI's category (or "correct"); otherwise the
 * next one in order. */
export function nextCategory(
  current: ErrorCategory | null,
  start: ErrorCategory | null,
): ErrorCategory {
  if (current === null) return start ?? "correct";
  const index = ERROR_CATEGORIES.indexOf(current);
  return ERROR_CATEGORIES[(index + 1) % ERROR_CATEGORIES.length] ?? "correct";
}
