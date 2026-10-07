// Every colour the plot_point canvas draws with, in one place (docs/plans/t7-plot-the-point.md,
// P5). A canvas is painted by code, so Tailwind classes cannot reach it: the colours come from the
// theme's tokens (docs/plans/t9-theming.md, "Canvas mapping"), read on every draw, and PlotCanvas
// redraws when the theme changes.

import { tokenColor } from '../theme/theme';

export interface PlotPalette {
  background: string;
  grid: string;
  axis: string;
  tickLabel: string;
  overlay: string;
  overlayLabel: string;
  point: string;
  pointOutline: string;
}

/** The palette to draw with now, from the current theme's tokens (call it on every draw). */
export function plotPalette(): PlotPalette {
  return {
    background: tokenColor('page'),
    grid: tokenColor('line'),
    axis: tokenColor('fg-subtle'),
    tickLabel: tokenColor('fg-muted'),
    overlay: tokenColor('plot-overlay'),
    overlayLabel: tokenColor('plot-overlay'),
    point: tokenColor('plot-point'),
    pointOutline: tokenColor('page'),
  };
}
