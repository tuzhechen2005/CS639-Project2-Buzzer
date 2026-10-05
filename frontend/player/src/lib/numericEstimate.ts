// Display helpers for numeric_estimate questions. Everything here only formats; scoring and
// the band a player landed in are decided by the server (the player's points are matched to
// a band, never recomputed from the value).

import type { PlayerAnswerReveal } from '../types/game';

export type NumericReveal = Extract<PlayerAnswerReveal, { type: 'numeric_estimate' }>;

const formatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 });

/** en-US grouping, at most six decimals (hides floating-point noise in computed values). */
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

/** The band whose points equal what the server awarded (points strictly decrease, so it is unique). */
export function landedBandIndex(reveal: NumericReveal, points: number): number | null {
  const i = reveal.bands.findIndex((b) => b.points === points);
  return i === -1 ? null : i;
}

/** "Within 5 %" for the band the player landed in, or "More than 30 % off" for a miss. */
export function outcomeLine(reveal: NumericReveal, points: number, unit?: string): string {
  const i = landedBandIndex(reveal, points);
  if (i !== null) return bandLabel(reveal, reveal.bands[i].within, unit);
  const last = reveal.bands[reveal.bands.length - 1];
  if (!last) return '';
  return reveal.mode === 'relative'
    ? `More than ${formatNumber(last.within)} % off`
    : `More than ${withUnit(last.within, unit)} off`;
}

/** "35 steps off" (the absolute difference, formatted; no percentage is computed). */
export function differenceLine(value: number, target: number, unit?: string): string {
  return `${withUnit(Math.abs(value - target), unit)} off`;
}

/** Correct (the best band), close (a lower band) or incorrect (no points). */
export function numericVerdict(reveal: NumericReveal, points: number): 'correct' | 'close' | 'incorrect' {
  if (points <= 0 || reveal.bands.length === 0) return 'incorrect';
  return points >= reveal.bands[0].points ? 'correct' : 'close';
}
