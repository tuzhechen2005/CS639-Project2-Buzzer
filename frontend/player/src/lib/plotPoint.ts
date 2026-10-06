// The player's plot_point logic that is not drawing (docs/plans/t7-plot-the-point.md, P6):
// the typed-coordinates rules and the result text. Pure functions, so every rule is tested.
// Scoring is the server's: the band shown is the one whose points equal what it awarded.

import type { PlayerAnswerReveal, QuestionConfig } from '../types/game';
import { parseNumber } from './parseNumber';
import {
  cellDistance,
  formatCoord,
  formatGridPoint,
  graphToGrid,
  gridToGraph,
  type GridPoint,
  type PlotConfig,
} from './plotGeometry';

export type PlotReveal = Extract<PlayerAnswerReveal, { type: 'plot_point' }>;

const MINUS = '−';

/** The plane from a question config, or null if it is incomplete. */
export function plotConfigOf(c: QuestionConfig | undefined): PlotConfig | null {
  if (!c) return null;
  const { xMin, xMax, xStep, yMin, yMax, yStep } = c;
  const nums = [xMin, xMax, xStep, yMin, yMax, yStep];
  if (!nums.every((n) => typeof n === 'number' && Number.isFinite(n))) return null;
  return {
    xMin: xMin!, xMax: xMax!, xStep: xStep!, yMin: yMin!, yMax: yMax!, yStep: yStep!,
    xLabel: c.xLabel, yLabel: c.yLabel, overlays: c.overlays,
  };
}

/** {col, row} from an answer object, or null. */
export function gridPointOf(answer: unknown): GridPoint | null {
  if (!answer || typeof answer !== 'object') return null;
  const { col, row } = answer as { col?: unknown; row?: unknown };
  return Number.isInteger(col) && Number.isInteger(row) ? { col: col as number, row: row as number } : null;
}

// ---------------------------------------------------------------------------
// Typed coordinates (the "Type coordinates" panel)
// ---------------------------------------------------------------------------

export interface TypedState {
  point: GridPoint | null;
  xText: string;
  yText: string;
  /** "Enter both coordinates": one field was committed while the other could not be used. */
  needBoth: boolean;
}

export const EMPTY_TYPED: TypedState = { point: null, xText: '', yText: '', needBoth: false };

/** A field's text as a number: the field shows U+2212 for negatives; parseNumber is unchanged. */
export function parseCoordText(text: string): number | null {
  return parseNumber(text.replace(/−/g, '-'));
}

/** Both fields' text for a grid point (rounded to the steps, with U+2212). */
export function textsFor(c: PlotConfig, p: GridPoint): { xText: string; yText: string } {
  const g = gridToGraph(c, p);
  return { xText: formatCoord(g.x, c.xStep), yText: formatCoord(g.y, c.yStep) };
}

/** The state after the canvas placed or moved the point: both fields follow it. */
export function placedOnCanvas(c: PlotConfig, p: GridPoint): TypedState {
  return { point: p, ...textsFor(c, p), needBoth: false };
}

/**
 * Commit one field (on blur, Enter, ± or Submit). Values are clamped to the plane and snapped
 * to the nearest grid point, and the field then shows the snapped value.
 * - No point yet: placed only when BOTH fields parse; otherwise nothing is placed, the text
 *   stays as typed and needBoth is set (if this field has text).
 * - Point exists: only this field's axis moves; unparsable text reverts to the point's value.
 */
export function commitAxis(c: PlotConfig, s: TypedState, axis: 'x' | 'y'): TypedState {
  const x = parseCoordText(s.xText);
  const y = parseCoordText(s.yText);
  if (s.point === null) {
    if (x !== null && y !== null) return placedOnCanvas(c, graphToGrid(c, { x, y }));
    const text = axis === 'x' ? s.xText : s.yText;
    return { ...s, needBoth: text.trim() !== '' || s.needBoth };
  }
  const value = axis === 'x' ? x : y;
  const current = textsFor(c, s.point);
  if (value === null) {
    return axis === 'x' ? { ...s, xText: current.xText, needBoth: false } : { ...s, yText: current.yText, needBoth: false };
  }
  const here = gridToGraph(c, s.point);
  const snapped = graphToGrid(c, axis === 'x' ? { x: value, y: here.y } : { x: here.x, y: value });
  const point = axis === 'x' ? { col: snapped.col, row: s.point.row } : { col: s.point.col, row: snapped.row };
  const texts = textsFor(c, point);
  return axis === 'x'
    ? { ...s, point, xText: texts.xText, needBoth: false }
    : { ...s, point, yText: texts.yText, needBoth: false };
}

/** Submit commits both fields synchronously, then sends the resulting point (or nothing). */
export function commitForSubmit(c: PlotConfig, s: TypedState): TypedState {
  return commitAxis(c, commitAxis(c, s, 'x'), 'y');
}

/** Submit is enabled when a point exists or both fields hold text parseNumber accepts. */
export function canSubmitTyped(s: TypedState): boolean {
  return s.point !== null || (parseCoordText(s.xText) !== null && parseCoordText(s.yText) !== null);
}

/** ±: flip the sign of a field's text. An empty field gets "−" (and nothing is committed). */
export function flipSign(text: string): string {
  const t = text.trim();
  if (t === '') return MINUS;
  if (t.startsWith(MINUS) || t.startsWith('-')) return t.slice(1);
  return MINUS + t;
}

// ---------------------------------------------------------------------------
// Result text (results screen and game-over list)
// ---------------------------------------------------------------------------

export function distanceText(d: number): string {
  if (d === 0) return 'Exact';
  return d === 1 ? '1 cell off' : `${d} cells off`;
}

function pointsText(points: number): string {
  return `${Number(points.toFixed(2)).toLocaleString('en-US')} pts`;
}

/** The reveal's target as a grid point (it is always a grid point; snapping hides float noise). */
export function targetCell(c: PlotConfig, reveal: PlotReveal): GridPoint {
  return graphToGrid(c, reveal.target);
}

/**
 * One line, e.g. "You: (4, −2) · Target: (3, −2) · 1 cell off · 50 pts".
 * No answer: "Target: (3, −2)". COMPLETENESS (reveal null): "Answer recorded: (4, −2)".
 */
export function plotResultLine(
  c: PlotConfig,
  reveal: PlotReveal | null,
  answer: GridPoint | null,
  points: number,
): string {
  if (reveal === null) return answer ? `Answer recorded: ${formatGridPoint(c, answer)}` : '';
  const target = targetCell(c, reveal);
  const targetText = `Target: ${formatGridPoint(c, target)}`;
  if (answer === null) return targetText;
  return [
    `You: ${formatGridPoint(c, answer)}`,
    targetText,
    distanceText(cellDistance(answer, target)),
    pointsText(points),
  ].join(' · ');
}

/** Correct (the first band's points), close (fewer, > 0) or incorrect (0). */
export function plotVerdict(reveal: PlotReveal, points: number): 'correct' | 'close' | 'incorrect' {
  if (points <= 0 || reveal.bands.length === 0) return 'incorrect';
  return points >= reveal.bands[0].points ? 'correct' : 'close';
}
