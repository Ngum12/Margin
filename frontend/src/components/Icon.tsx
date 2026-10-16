import { createElement } from "react";

import { ICONS } from "./icons";
import type { IconName } from "./icons";

/** A bundled Lucide icon. Decorative by default (hidden from screen readers): the control or
 * text next to it carries the meaning. Pass `label` only when the icon stands alone. */
export function Icon({
  name,
  size = 18,
  label,
}: {
  name: IconName;
  size?: number;
  label?: string;
}) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
    >
      {ICONS[name].map(([tag, attrs], index) => createElement(tag, { key: index, ...attrs }))}
    </svg>
  );
}
