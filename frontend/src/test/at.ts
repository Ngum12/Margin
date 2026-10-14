/** Element at `index`, failing the test clearly if it is missing (instead of a `!` assertion). */
export function at<T>(items: readonly T[], index: number): T {
  const item = items[index];
  if (item === undefined) throw new Error(`No item at index ${String(index)}`);
  return item;
}
