import { useEffect } from "react";

import { api } from "../api/endpoints";

export const HEARTBEAT_MS = 30_000;
export const IDLE_MS = 5 * 60_000;

/** Review time (owner change 2): while the review screen is visible and has been used in the
 * last 5 minutes, tell the local server every 30 seconds. The first call opens the session.
 * It goes only to the Margin server, never anywhere else (D-052). */
export function useHeartbeat(scriptId: number, enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    let lastActivity = Date.now();
    const touch = () => {
      lastActivity = Date.now();
    };
    const beat = () => {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastActivity > IDLE_MS) return;
      api.reviewHeartbeat(scriptId).catch(() => {
        // Review time is a measure, never a reason to interrupt the teacher.
      });
    };
    beat();
    const events = ["keydown", "pointerdown", "wheel"] as const;
    for (const name of events) window.addEventListener(name, touch, { passive: true });
    const timer = window.setInterval(beat, HEARTBEAT_MS);
    return () => {
      window.clearInterval(timer);
      for (const name of events) window.removeEventListener(name, touch);
    };
  }, [scriptId, enabled]);
}
