import type { RedPenMark } from "../api/types";

const RED = "#d01212";

/** The red pen drawn over a page image (owner, 2026-10-15): the same layout as the marked PDF.
 *
 * The overlay sits on the stored image and turns with it, so its marks are drawn in the
 * upright page's frame (fractions from the server) and turned back to the stored frame here.
 * Marks still based on the AI's proposal (no teacher decision yet) are drawn lighter. */
export function RedPenOverlay({
  marks,
  width,
  height,
  rotation,
}: {
  marks: RedPenMark[];
  width: number; // stored image size in pixels
  height: number;
  rotation: number; // clockwise degrees applied to show the page upright
}) {
  const sideways = rotation % 180 !== 0;
  const uprightW = sideways ? height : width;
  const uprightH = sideways ? width : height;
  const turnBack = `translate(${String(width / 2)} ${String(height / 2)}) rotate(${String(-rotation)}) translate(${String(-uprightW / 2)} ${String(-uprightH / 2)})`;

  return (
    <svg
      className="red-pen"
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      data-testid="red-pen"
    >
      <g transform={turnBack}>
        {marks.map((mark, index) => (
          <RedPenShape
            key={`${mark.kind}-${String(index)}`}
            mark={mark}
            w={uprightW}
            h={uprightH}
          />
        ))}
      </g>
    </svg>
  );
}

function RedPenShape({ mark, w, h }: { mark: RedPenMark; w: number; h: number }) {
  const x = mark.x * w;
  const y = mark.y * h;
  const s = mark.size * h;
  const opacity = mark.pending ? 0.4 : 1;
  const stroke = {
    stroke: RED,
    strokeWidth: Math.max(2, s * 0.085),
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    fill: "none",
    opacity,
  };
  const tick = `M ${String(x)} ${String(y - s * 0.05)} L ${String(x + s * 0.28)} ${String(y + s * 0.35)} L ${String(x + s * 0.95)} ${String(y - s * 0.62)}`;
  switch (mark.kind) {
    case "tick":
      return <path d={tick} {...stroke} data-kind="tick" />;
    case "partial":
      return (
        <g data-kind="partial" opacity={opacity}>
          <path d={tick} {...stroke} opacity={1} />
          <text
            x={x + s * 1.03}
            y={y + s * 0.1}
            className="red-pen-text"
            fontSize={s * 0.55}
            fill={RED}
          >
            {mark.text}
          </text>
        </g>
      );
    case "cross":
      return (
        <g data-kind="cross">
          <line x1={x} y1={y + s * 0.3} x2={x + s * 0.6} y2={y - s * 0.3} {...stroke} />
          <line x1={x} y1={y - s * 0.3} x2={x + s * 0.6} y2={y + s * 0.3} {...stroke} />
        </g>
      );
    case "score":
      return (
        <text
          x={x}
          y={y + s * 0.3}
          textAnchor="end"
          className="red-pen-text"
          fontSize={s * 0.95}
          fill={RED}
          opacity={opacity}
          data-kind="score"
        >
          {mark.text}
        </text>
      );
    case "total":
      return (
        <g data-kind="total" opacity={opacity}>
          <ellipse
            cx={x + s * 1.1}
            cy={y}
            rx={s * 1.55}
            ry={s * 0.6}
            {...stroke}
            strokeWidth={Math.max(2, s * 0.06)}
            opacity={1}
          />
          <text x={x} y={y + s * 0.3} className="red-pen-text" fontSize={s * 0.95} fill={RED}>
            {mark.text}
          </text>
        </g>
      );
    case "comment":
      return (
        <foreignObject x={x} y={y} width={mark.width * w} height={s * 3.6} data-kind="comment">
          <div className="red-pen-comment" style={{ fontSize: `${String(s * 1.0)}px` }}>
            {mark.text}
          </div>
        </foreignObject>
      );
  }
}
