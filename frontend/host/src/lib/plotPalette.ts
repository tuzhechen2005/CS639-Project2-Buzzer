// Every colour the host's plot_point canvas draws with, in one place
// (docs/plans/t7-plot-the-point.md, P5). A canvas is painted by code, so Tailwind classes cannot
// reach it: T9 switches these to the theme's colour tokens here, and the canvas redraws when the
// theme changes.

export interface PlotPalette {
  background: string;
  grid: string;
  axis: string;
  tickLabel: string;
  overlay: string;
  overlayLabel: string;
  /** Answer dots on the results scatter. */
  dot: string;
  dotLabel: string;
  /** The target star. */
  target: string;
  targetOutline: string;
  /** Band squares around the target: the best band, then the others. */
  bandBest: string;
  band: string;
  bandLabel: string;
}

const DARK: PlotPalette = {
  background: '#0f172a', // slate-900, the app background
  grid: '#1e293b', // slate-800
  axis: '#64748b', // slate-500
  tickLabel: '#94a3b8', // slate-400
  overlay: '#38bdf8', // sky-400
  overlayLabel: '#7dd3fc', // sky-300
  dot: '#818cf8', // indigo-400
  dotLabel: '#e0e7ff', // indigo-100
  target: '#22c55e', // green-500, as "correct" elsewhere on the host screens
  targetOutline: '#dcfce7', // green-100
  bandBest: '#22c55e', // green-500
  band: '#a3a3a3', // neutral-400
  bandLabel: '#cbd5e1', // slate-300
};

/** The palette to draw with now. Today the app has one (dark) theme. */
export function plotPalette(): PlotPalette {
  return DARK;
}
