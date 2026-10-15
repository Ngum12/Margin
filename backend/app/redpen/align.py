"""Match the transcription's lines to the lines of ink found on the page.

Both run top to bottom, so the match keeps their order. One transcription line may cover up to
three lines of ink (the reader often joins a line the student wrapped), and a stray mark or a
line the reader left out may be skipped at a cost. Text length predicts ink width: the page's
own ratio of characters to ink width is used, so handwriting size does not matter. The match is
accepted only when it fits well; otherwise the caller falls back to marks in the margin.
"""

from dataclasses import dataclass

from app.redpen.ink import Band

MAX_GROUP = 3
SKIP_BAND = 0.25  # cost of a line of ink matched to no text (stray marks, crossings-out)
SKIP_LINE = 0.35  # cost of a text line with no ink (e.g. "[DIAGRAM]")
MAX_MEAN_COST = 0.12  # per text line, in page widths
MAX_SKIPS = 2


@dataclass(frozen=True)
class Alignment:
    # For each transcription line index: (first band, last band) inclusive, or None.
    lines: dict[int, tuple[int, int]]
    mean_cost: float
    skips: int

    @property
    def confident(self) -> bool:
        return self.mean_cost <= MAX_MEAN_COST and self.skips <= MAX_SKIPS


def align(text_lines: list[str], bands: list[Band]) -> Alignment | None:
    """``text_lines`` is the page's transcription split on line breaks (blank lines allowed)."""
    lines = [(i, line.strip()) for i, line in enumerate(text_lines) if line.strip()]
    if not lines or not bands:
        return None
    total_chars = sum(len(text) for _, text in lines)
    total_width = sum(b.width for b in bands)
    per_char = total_width / total_chars if total_chars else 0.0

    n, m = len(lines), len(bands)
    inf = float("inf")
    # cost[i][j]: best cost matching the first i text lines to the first j bands.
    cost = [[inf] * (m + 1) for _ in range(n + 1)]
    step: list[list[tuple[int, int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            here = cost[i][j]
            if here == inf:
                continue
            if j < m and here + SKIP_BAND < cost[i][j + 1]:  # band with no text
                cost[i][j + 1] = here + SKIP_BAND
                step[i][j + 1] = (i, j, 0)
            if i < n and here + SKIP_LINE < cost[i + 1][j]:  # text with no band
                cost[i + 1][j] = here + SKIP_LINE
                step[i + 1][j] = (i, j, -1)
            if i < n:
                predicted = len(lines[i][1]) * per_char
                for size in range(1, MAX_GROUP + 1):
                    if j + size > m:
                        break
                    width = sum(b.width for b in bands[j : j + size])
                    value = here + abs(predicted - width) + 0.02 * (size - 1)
                    if value < cost[i + 1][j + size]:
                        cost[i + 1][j + size] = value
                        step[i + 1][j + size] = (i, j, size)

    matched: dict[int, tuple[int, int]] = {}
    skips, total = 0, cost[n][m]
    i, j = n, m
    while (i, j) != (0, 0):
        previous = step[i][j]
        if previous is None:  # pragma: no cover - every cell reached has a step
            return None
        pi, pj, size = previous
        if size > 0:
            matched[lines[pi][0]] = (pj, pj + size - 1)
        else:
            skips += 1
        i, j = pi, pj
    return Alignment(matched, total / n, skips)
