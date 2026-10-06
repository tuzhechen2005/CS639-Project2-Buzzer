// Host helpers for plot_point (docs/plans/t7-plot-the-point.md, P7) that are not drawing.

import type { AnswerReveal, QuestionConfig } from '../types/game';
import { formatGridPoint, graphToGrid, type PlotConfig } from './plotGeometry';

export type PlotReveal = Extract<AnswerReveal, { type: 'plot_point' }>;

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

export function plotRevealOf(reveal: AnswerReveal | undefined): PlotReveal | null {
  return reveal && reveal.type === 'plot_point' ? (reveal as PlotReveal) : null;
}

/** "(3, −2)": the target snapped to its grid point, so float noise never shows. */
export function targetText(c: PlotConfig, reveal: PlotReveal): string {
  return formatGridPoint(c, graphToGrid(c, reveal.target));
}
