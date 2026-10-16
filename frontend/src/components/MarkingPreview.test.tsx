import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarkingPreview } from "./MarkingPreview";

// The animation is optional: controls and reduced-motion preferences must remain reliable.
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("marking journey", () => {
  it("advances, pauses, and lets a teacher explore a specific step", () => {
    vi.useFakeTimers();
    render(<MarkingPreview />);
    expect(screen.getByRole("button", { name: /01.*Scan/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    act(() => {
      vi.advanceTimersByTime(4200);
    });
    expect(screen.getByRole("button", { name: /02.*Read/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Pause animation" }));
    act(() => {
      vi.advanceTimersByTime(8400);
    });
    expect(screen.getByRole("button", { name: /02.*Read/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: /04.*Review/ }));
    expect(screen.getByRole("button", { name: /04.*Review/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
    act(() => {
      vi.advanceTimersByTime(4200);
    });
    expect(screen.getByRole("button", { name: /01.*Scan/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("does not advance automatically when reduced motion is requested", () => {
    vi.useFakeTimers();
    const remove = vi.fn();
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: remove })),
    );
    const { unmount } = render(<MarkingPreview />);
    act(() => {
      vi.advanceTimersByTime(16800);
    });
    expect(screen.getByRole("button", { name: /01.*Scan/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.queryByRole("button", { name: "Pause animation" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /03.*Propose/ }));
    expect(screen.getByRole("button", { name: /03.*Propose/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    unmount();
    expect(remove).toHaveBeenCalled();
  });
});
