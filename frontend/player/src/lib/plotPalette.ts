// Every colour the plot_point canvas draws with, in one place (docs/plans/t7-plot-the-point.md,
// P5). A canvas is painted by code, so Tailwind classes cannot reach it: T9 switches these to
// the theme's colour tokens here, and the canvas redraws when the theme changes.

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

const DARK: PlotPalette = {
  background: '#0f172a', // slate-900, the app background
  grid: '#1e293b', // slate-800
  axis: '#64748b', // slate-500
  tickLabel: '#94a3b8', // slate-400
  overlay: '#38bdf8', // sky-400
  overlayLabel: '#7dd3fc', // sky-300
  point: '#f59e0b', // amber-500, the player's point
  pointOutline: '#fef3c7', // amber-100
};

/** The palette to draw with now. Today the app has one (dark) theme. */
export function plotPalette(): PlotPalette {
  return DARK;
}
