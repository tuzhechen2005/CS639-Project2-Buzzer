// Drawing the plot_point plane on a canvas (docs/plans/t7-plot-the-point.md, P7): background
// image, grid, axes, tick labels and overlays, as on the phone (the player app has its own copy,
// frontend/player/src/lib/plotDraw.ts; the apps share no code). `scale` enlarges text and margins
// for the projector. Margins, tick spacing and label placement are layout choices.

import {
  evaluatePolynomial,
  formatCoord,
  graphToPixel,
  gridToGraph,
  gridToPixel,
  inPlane,
  layoutPlot,
  lineCrossings,
  polynomialPaths,
  type PlotConfig,
  type PlotLayout,
} from './plotGeometry';
import type { PlotPalette } from './plotPalette';

/** Room around the plot for the tick labels: y labels on the left, x labels below. */
export function plotMargin(scale = 1) {
  return { left: 34 * scale, right: 10 * scale, top: 10 * scale, bottom: 22 * scale };
}

const font = (scale: number) => `${11 * scale}px system-ui, -apple-system, sans-serif`;
const labelFont = (scale: number) => `600 ${12 * scale}px system-ui, -apple-system, sans-serif`;

export function plotLayoutFor(c: PlotConfig, width: number, height: number, scale = 1): PlotLayout {
  return layoutPlot(c, width, height, plotMargin(scale));
}

/** Label every k-th grid line, k chosen so labels are at least minPx apart; 0 is always one. */
function labelEvery(cellPx: number, minPx: number): number {
  for (const k of [1, 2, 4, 5, 10, 20]) if (k * cellPx >= minPx) return k;
  return 20;
}

function isLabelled(value: number, step: number, k: number): boolean {
  return Math.round(value / step) % k === 0;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Text near (px, py), kept inside the plot rectangle, with a halo so it reads over lines. */
function labelAt(
  ctx: CanvasRenderingContext2D,
  l: PlotLayout,
  palette: PlotPalette,
  text: string,
  px: number,
  py: number,
  scale: number,
) {
  const w = ctx.measureText(text).width;
  const x = clamp(px + 6 * scale, l.left + 2, l.left + l.width - w - 2);
  const y = clamp(py - 6 * scale, l.top + 13 * scale, l.top + l.height - 4);
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  ctx.lineWidth = 4 * scale;
  ctx.strokeStyle = palette.background;
  ctx.strokeText(text, x, y);
  ctx.fillStyle = palette.overlayLabel;
  ctx.fillText(text, x, y);
}

/** The height a box of this width needs for the plane with square cells (for portrait). */
export function plotHeightForWidth(c: PlotConfig, width: number, scale = 1): number {
  const m = plotMargin(scale);
  const l = layoutPlot(c, width, Number.MAX_SAFE_INTEGER, m);
  return l.height + m.top + m.bottom;
}

/**
 * Paint the whole plane: background, the optional image stretched to the plot area, grid,
 * axes (at 0, or along the nearest edge when 0 is outside the range), tick labels, axis
 * labels and overlays. Overlays are clipped to the plot; point overlays outside it are skipped.
 */
export function drawPlane(
  ctx: CanvasRenderingContext2D,
  c: PlotConfig,
  l: PlotLayout,
  palette: PlotPalette,
  cssWidth: number,
  cssHeight: number,
  image: HTMLImageElement | null,
  scale = 1,
): void {
  ctx.fillStyle = palette.background;
  ctx.fillRect(0, 0, cssWidth, cssHeight);
  if (l.cellPx <= 0) return;
  const right = l.left + l.width;
  const bottom = l.top + l.height;

  if (image) ctx.drawImage(image, l.left, l.top, l.width, l.height);

  // Grid
  ctx.strokeStyle = palette.grid;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let col = 0; col <= l.nCols; col++) {
    const { px } = gridToPixel(l, { col, row: 0 });
    ctx.moveTo(px, l.top);
    ctx.lineTo(px, bottom);
  }
  for (let row = 0; row <= l.nRows; row++) {
    const { py } = gridToPixel(l, { col: 0, row });
    ctx.moveTo(l.left, py);
    ctx.lineTo(right, py);
  }
  ctx.stroke();

  // Axes at x = 0 and y = 0, clamped to the plane's edges.
  const origin = graphToPixel(c, l, { x: clamp(0, c.xMin, c.xMax), y: clamp(0, c.yMin, c.yMax) });
  ctx.strokeStyle = palette.axis;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(l.left, origin.py);
  ctx.lineTo(right, origin.py);
  ctx.moveTo(origin.px, l.top);
  ctx.lineTo(origin.px, bottom);
  ctx.stroke();

  // Tick labels: x below the plot, y to its left.
  ctx.fillStyle = palette.tickLabel;
  ctx.font = font(scale);
  const kx = labelEvery(l.cellPx, 30 * scale);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (let col = 0; col <= l.nCols; col++) {
    const { x } = gridToGraph(c, { col, row: 0 });
    if (!isLabelled(x, c.xStep, kx)) continue;
    ctx.fillText(formatCoord(x, c.xStep), gridToPixel(l, { col, row: 0 }).px, bottom + 4 * scale);
  }
  const ky = labelEvery(l.cellPx, 16 * scale);
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let row = 0; row <= l.nRows; row++) {
    const { y } = gridToGraph(c, { col: 0, row });
    if (!isLabelled(y, c.yStep, ky)) continue;
    ctx.fillText(formatCoord(y, c.yStep), l.left - 4 * scale, gridToPixel(l, { col: 0, row }).py);
  }

  // Axis names, inside the plot at the ends of the axes.
  ctx.font = labelFont(scale);
  if (c.xLabel) {
    ctx.textAlign = 'right';
    ctx.textBaseline = 'bottom';
    ctx.fillText(c.xLabel, right - 4, clamp(origin.py - 4, l.top + 14 * scale, bottom - 2));
  }
  if (c.yLabel) {
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(c.yLabel, clamp(origin.px + 6, l.left + 2, right - 40), l.top + 4);
  }

  drawOverlays(ctx, c, l, palette, scale);
}

function drawOverlays(ctx: CanvasRenderingContext2D, c: PlotConfig, l: PlotLayout, palette: PlotPalette, scale: number) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(l.left, l.top, l.width, l.height);
  ctx.clip();
  ctx.lineWidth = 2.5 * scale;
  ctx.lineJoin = 'round';
  ctx.font = labelFont(scale);
  for (const o of c.overlays ?? []) {
    let labelPos: { px: number; py: number } | null = null;
    ctx.strokeStyle = palette.overlay;
    ctx.fillStyle = palette.overlay;
    if (o.kind === 'point' && typeof o.x === 'number' && typeof o.y === 'number') {
      if (!inPlane(c, { x: o.x, y: o.y })) continue;
      const p = graphToPixel(c, l, { x: o.x, y: o.y });
      ctx.beginPath();
      ctx.arc(p.px, p.py, 4 * scale, 0, Math.PI * 2);
      ctx.fill();
      labelPos = p;
    } else if (o.kind === 'line' && [o.x1, o.y1, o.x2, o.y2].every((v) => typeof v === 'number')) {
      const hit = lineCrossings(c, { x1: o.x1!, y1: o.y1!, x2: o.x2!, y2: o.y2! });
      if (!hit) continue;
      const a = graphToPixel(c, l, hit[0]);
      const b = graphToPixel(c, l, hit[1]);
      ctx.beginPath();
      ctx.moveTo(a.px, a.py);
      ctx.lineTo(b.px, b.py);
      ctx.stroke();
      labelPos = b.px >= a.px ? b : a;
      labelPos = { px: labelPos.px - 40 * scale, py: labelPos.py };
    } else if (o.kind === 'polynomial' && Array.isArray(o.coefficients) && o.coefficients.length > 0) {
      const paths = polynomialPaths(c, l, o.coefficients);
      for (const path of paths) {
        ctx.beginPath();
        path.forEach((p, i) => (i === 0 ? ctx.moveTo(p.px, p.py) : ctx.lineTo(p.px, p.py)));
        ctx.stroke();
      }
      if (paths.length > 0) {
        const last = paths[paths.length - 1];
        const end = last[last.length - 1];
        labelPos = { px: end.px - 40 * scale, py: end.py };
        // Keep the label beside the curve where it is, not off its end.
        const x = c.xMin + ((labelPos.px - l.left) / l.cellPx) * c.xStep;
        const y = evaluatePolynomial(o.coefficients, x);
        if (Number.isFinite(y) && inPlane(c, { x, y })) labelPos = graphToPixel(c, l, { x, y });
      }
    } else {
      continue;
    }
    if (o.label && labelPos) labelAt(ctx, l, palette, o.label, labelPos.px, labelPos.py, scale);
    ctx.lineWidth = 2.5 * scale;
  }
  ctx.restore();
}

/** "Coordinate plane, x from −10 to 10, y from −10 to 10" for the canvas's aria-label. */
export function planeDescription(c: PlotConfig): string {
  return (
    `Coordinate plane, x from ${formatCoord(c.xMin, c.xStep)} to ${formatCoord(c.xMax, c.xStep)}, ` +
    `y from ${formatCoord(c.yMin, c.yStep)} to ${formatCoord(c.yMax, c.yStep)}`
  );
}
