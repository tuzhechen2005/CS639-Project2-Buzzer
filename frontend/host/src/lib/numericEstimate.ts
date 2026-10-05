// Display helpers for numeric_estimate questions on the host screens.

import type { AnswerReveal } from '../types/game';

export type NumericReveal = Extract<AnswerReveal, { type: 'numeric_estimate' }>;

const formatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 });

/** en-US grouping, at most six decimals (the same rule as the player app). */
export function formatNumber(n: number): string {
  return formatter.format(n === 0 ? 0 : n);
}

export function withUnit(n: number, unit?: string): string {
  return unit ? `${formatNumber(n)} ${unit}` : formatNumber(n);
}

/** "Within 5 %" (relative) or "Within ±3 steps" (absolute). */
export function bandLabel(reveal: NumericReveal, within: number, unit?: string): string {
  return reveal.mode === 'relative'
    ? `Within ${formatNumber(within)} %`
    : `Within ±${withUnit(within, unit)}`;
}

export interface NumericBar {
  label: string;
  count: number;
  correct: boolean | null;
}

/**
 * One bar per band in order (key "0", "1", …), then "Missed" (key "miss"). Bars with no
 * answers are still drawn, so the host sees the whole band structure. The best band is the
 * correct one; the others have no verdict.
 */
export function buildNumericBars(
  reveal: NumericReveal,
  distribution: Record<string, number>,
  unit?: string,
): NumericBar[] {
  const bars: NumericBar[] = reveal.bands.map((band, i) => ({
    label: bandLabel(reveal, band.within, unit),
    count: distribution[String(i)] ?? 0,
    correct: i === 0 ? true : null,
  }));
  bars.push({ label: 'Missed', count: distribution['miss'] ?? 0, correct: null });
  return bars;
}
