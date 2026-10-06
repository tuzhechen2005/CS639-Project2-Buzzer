// Geometry for plot_point questions (docs/plans/t7-plot-the-point.md, P5): grid size,
// grid <-> graph units <-> pixels, snapping, cell distance, overlay clipping and number
// formatting. Pure functions only.
//
// THIS FILE IS BYTE-IDENTICAL in frontend/player/src/lib/ and frontend/host/src/lib/
// (tests/unit/test_plot_geometry_copies.py fails if they differ). Edit both together. It
// imports nothing, because the two apps' types differ: it declares its own minimal input
// types, which each app's question config satisfies structurally.
//
// Conventions: a grid point has whole-number indices col (0 at xMin, rightwards) and row
// (0 at yMin, UPWARDS). Canvas y grows downwards, so the top-left of the plot area is
// (xMin, yMax): row r sits at top + (nRows - r) * cellPx.

export interface PlotOverlay {
  kind: string;
  x?: number;
  y?: number;
  x1?: number;
  y1?: number;
  x2?: number;
  y2?: number;
  coefficients?: number[];
  label?: string | null;
}

export interface PlotConfig {
  xMin: number;
  xMax: number;
  xStep: number;
  yMin: number;
  yMax: number;
  yStep: number;
  xLabel?: string | null;
  yLabel?: string | null;
  overlays?: PlotOverlay[] | null;
}

export interface GridPoint {
  col: number;
  row: number;
}

export interface Pixel {
  px: number;
  py: number;
}

export interface GraphPoint {
  x: number;
  y: number;
}

/** The plot rectangle in CSS pixels: square cells of cellPx, nCols x nRows of them. */
export interface PlotLayout {
  left: number;
  top: number;
  cellPx: number;
  width: number;
  height: number;
  nCols: number;
  nRows: number;
}

// ---------------------------------------------------------------------------
// Grid size and numbers
// ---------------------------------------------------------------------------

/** nCols / nRows, rounded exactly like the server (P1 rule 4): never floor the quotient. */
export function gridSize(c: PlotConfig): { nCols: number; nRows: number } {
  return {
    nCols: Math.round((c.xMax - c.xMin) / c.xStep),
    nRows: Math.round((c.yMax - c.yMin) / c.yStep),
  };
}

/** Decimal places of a step (1, 2 or 5 x 10^k): max(0, -k). Same rule as the report. */
export function stepDecimals(step: number): number {
  return Math.max(0, -Math.floor(Math.log10(step) + 1e-9));
}

/** v rounded to the step's decimals, as a plain number (0.1 * 3 -> 0.3; never -0). */
export function roundToStep(v: number, step: number): number {
  const r = Number(v.toFixed(stepDecimals(step)));
  return r === 0 ? 0 : r;
}

/** A coordinate for display: rounded to the step's decimals, with a typographic minus
 * (U+2212). Display only; never parsed back. */
export function formatCoord(v: number, step: number): string {
  return String(roundToStep(v, step)).replace('-', '−');
}

/** "(3, −2)" for a grid point. */
export function formatGridPoint(c: PlotConfig, p: GridPoint): string {
  const g = gridToGraph(c, p);
  return `(${formatCoord(g.x, c.xStep)}, ${formatCoord(g.y, c.yStep)})`;
}

// ---------------------------------------------------------------------------
// Grid <-> graph units
// ---------------------------------------------------------------------------

/** The graph-unit coordinates of a grid point, rounded to the steps (no float noise). */
export function gridToGraph(c: PlotConfig, p: GridPoint): GraphPoint {
  return {
    x: roundToStep(c.xMin + p.col * c.xStep, c.xStep),
    y: roundToStep(c.yMin + p.row * c.yStep, c.yStep),
  };
}

/** Nearest index for a fractional one, clamped to 0..n. Exactly midway rounds UP. */
export function snapIndex(raw: number, n: number): number {
  return Math.min(Math.max(Math.floor(raw + 0.5), 0), n);
}

/** The grid point nearest to a graph-unit point, clamped to the plane (typed values). */
export function graphToGrid(c: PlotConfig, g: GraphPoint): GridPoint {
  const { nCols, nRows } = gridSize(c);
  return {
    col: snapIndex((g.x - c.xMin) / c.xStep, nCols),
    row: snapIndex((g.y - c.yMin) / c.yStep, nRows),
  };
}

/** Cell distance max(|dcol|, |drow|): the server's scoring distance. */
export function cellDistance(a: GridPoint, b: GridPoint): number {
  return Math.max(Math.abs(a.col - b.col), Math.abs(a.row - b.row));
}

export function inPlane(c: PlotConfig, g: GraphPoint): boolean {
  return g.x >= c.xMin && g.x <= c.xMax && g.y >= c.yMin && g.y <= c.yMax;
}

// ---------------------------------------------------------------------------
// Layout and pixels
// ---------------------------------------------------------------------------

/**
 * The largest plot rectangle with square cells that fits in width x height after the margins,
 * centred horizontally. Margins leave room for tick and axis labels.
 */
export function layoutPlot(
  c: PlotConfig,
  width: number,
  height: number,
  margin: { left: number; right: number; top: number; bottom: number },
): PlotLayout {
  const { nCols, nRows } = gridSize(c);
  const availW = Math.max(0, width - margin.left - margin.right);
  const availH = Math.max(0, height - margin.top - margin.bottom);
  const cellPx = Math.max(0, Math.min(availW / nCols, availH / nRows));
  const plotW = cellPx * nCols;
  const plotH = cellPx * nRows;
  return {
    left: margin.left + (availW - plotW) / 2,
    top: margin.top,
    cellPx,
    width: plotW,
    height: plotH,
    nCols,
    nRows,
  };
}

export function gridToPixel(l: PlotLayout, p: GridPoint): Pixel {
  return { px: l.left + p.col * l.cellPx, py: l.top + (l.nRows - p.row) * l.cellPx };
}

/** The grid point nearest to a pixel, clamped to the plane (taps outside snap to the edge). */
export function pixelToGrid(l: PlotLayout, p: Pixel): GridPoint {
  if (l.cellPx <= 0) return { col: 0, row: 0 };
  return {
    col: snapIndex((p.px - l.left) / l.cellPx, l.nCols),
    row: snapIndex(l.nRows - (p.py - l.top) / l.cellPx, l.nRows),
  };
}

/** Any graph-unit point (not only grid points) to pixels; used for overlays. */
export function graphToPixel(c: PlotConfig, l: PlotLayout, g: GraphPoint): Pixel {
  return {
    px: l.left + ((g.x - c.xMin) / c.xStep) * l.cellPx,
    py: l.top + ((c.yMax - g.y) / c.yStep) * l.cellPx,
  };
}

// ---------------------------------------------------------------------------
// Overlays
// ---------------------------------------------------------------------------

export function evaluatePolynomial(coefficients: number[], x: number): number {
  // Horner's rule on [c0, c1, c2, c3] meaning c0 + c1 x + c2 x^2 + c3 x^3
  let y = 0;
  for (let i = coefficients.length - 1; i >= 0; i--) y = y * x + coefficients[i];
  return y;
}

/**
 * Where the INFINITE line through (x1, y1) and (x2, y2) crosses the plane's edges, as two
 * graph-unit points, or null if it misses the plane. Vertical and horizontal lines work.
 */
export function lineCrossings(
  c: PlotConfig,
  line: { x1: number; y1: number; x2: number; y2: number },
): [GraphPoint, GraphPoint] | null {
  const dx = line.x2 - line.x1;
  const dy = line.y2 - line.y1;
  if (dx === 0 && dy === 0) return null;
  // Liang-Barsky with an unbounded parameter range: clip x1 + t*d to the rectangle.
  let tMin = -Infinity;
  let tMax = Infinity;
  const clip = (d: number, lo: number, hi: number, start: number): boolean => {
    if (d === 0) return start >= lo && start <= hi;
    const a = (lo - start) / d;
    const b = (hi - start) / d;
    tMin = Math.max(tMin, Math.min(a, b));
    tMax = Math.min(tMax, Math.max(a, b));
    return true;
  };
  if (!clip(dx, c.xMin, c.xMax, line.x1) || !clip(dy, c.yMin, c.yMax, line.y1)) return null;
  if (tMin > tMax) return null;
  return [
    { x: line.x1 + tMin * dx, y: line.y1 + tMin * dy },
    { x: line.x1 + tMax * dx, y: line.y1 + tMax * dy },
  ];
}

/**
 * A polynomial sampled every `samplePx` pixels across the plot width, as pixel polylines
 * clipped to the plane: a new polyline starts wherever the curve re-enters, and each piece
 * ends exactly on the edge where it leaves.
 */
export function polynomialPaths(
  c: PlotConfig,
  l: PlotLayout,
  coefficients: number[],
  samplePx = 2,
): Pixel[][] {
  if (l.cellPx <= 0 || coefficients.length === 0) return [];
  const steps = Math.max(1, Math.ceil(l.width / samplePx));
  const samples: GraphPoint[] = [];
  for (let i = 0; i <= steps; i++) {
    const x = c.xMin + (c.xMax - c.xMin) * (i / steps);
    samples.push({ x, y: evaluatePolynomial(coefficients, x) });
  }
  const inside = (g: GraphPoint) => Number.isFinite(g.y) && g.y >= c.yMin && g.y <= c.yMax;
  // The point on segment a-b where y crosses the nearer of yMin / yMax.
  const edge = (a: GraphPoint, b: GraphPoint): GraphPoint => {
    const bound = (inside(a) ? b.y : a.y) > c.yMax ? c.yMax : c.yMin;
    const t = (bound - a.y) / (b.y - a.y);
    return { x: a.x + t * (b.x - a.x), y: bound };
  };
  const paths: Pixel[][] = [];
  let current: Pixel[] = [];
  for (let i = 0; i < samples.length; i++) {
    const g = samples[i];
    const prev = i > 0 ? samples[i - 1] : null;
    if (inside(g)) {
      if (prev && !inside(prev) && Number.isFinite(prev.y)) current.push(graphToPixel(c, l, edge(prev, g)));
      current.push(graphToPixel(c, l, g));
    } else if (prev && inside(prev)) {
      if (Number.isFinite(g.y)) current.push(graphToPixel(c, l, edge(prev, g)));
      paths.push(current);
      current = [];
    }
  }
  if (current.length > 0) paths.push(current);
  return paths.filter((p) => p.length >= 2);
}
