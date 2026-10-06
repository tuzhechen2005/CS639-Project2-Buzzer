import { useEffect, useRef, useState } from 'react';
import { imageUrl } from '../lib/images';
import { drawPlane, plotHeightForWidth, plotLayoutFor } from '../lib/plotDraw';
import {
  formatCoord,
  graphToGrid,
  gridSize,
  gridToPixel,
  pixelToGrid,
  type GridPoint,
  type PlotConfig,
  type PlotLayout,
} from '../lib/plotGeometry';
import { plotPalette, type PlotPalette } from '../lib/plotPalette';

interface PlotScatterProps {
  config: PlotConfig;
  /** config.image_id: the plane's background (T8). Loads in the background, never blocks. */
  imageId?: string | null;
  /** The answer distribution, "col,row" -> count. Omitted on the question screen (no dots). */
  distribution?: Record<string, number>;
  /** ACCURACY reveal: the target star and the band squares. Omitted for COMPLETENESS. */
  reveal?: { target: { x: number; y: number }; bands: { within: number; points: number }[] } | null;
  /** Text and line size; larger for the projector. */
  scale?: number;
  /** Sizes the box; its height is capped at what the plane needs at its width. */
  className?: string;
  /** The editor preview: a click picks the nearest grid point (clamped to the plane). */
  onPick?: (p: GridPoint) => void;
}

/** "col,row" buckets that are grid points of this plane; anything else is ignored. */
export function parseBuckets(distribution: Record<string, number>, c: PlotConfig): { p: GridPoint; count: number }[] {
  const { nCols, nRows } = gridSize(c);
  const out: { p: GridPoint; count: number }[] = [];
  for (const [key, count] of Object.entries(distribution)) {
    const m = /^(\d+),(\d+)$/.exec(key);
    if (!m || !(count > 0)) continue;
    const p = { col: Number(m[1]), row: Number(m[2]) };
    if (p.col <= nCols && p.row <= nRows) out.push({ p, count });
  }
  return out;
}

function drawBands(
  ctx: CanvasRenderingContext2D,
  l: PlotLayout,
  target: GridPoint,
  bands: { within: number; points: number }[],
  palette: PlotPalette,
  scale: number,
) {
  // Band N holds the grid points within N cells: a square reaching half a cell past them.
  // Widest first, so the narrower (better) squares and their labels sit on top.
  ctx.save();
  ctx.beginPath();
  ctx.rect(l.left, l.top, l.width, l.height);
  ctx.clip();
  ctx.font = `600 ${11 * scale}px system-ui, -apple-system, sans-serif`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'bottom';
  const order = bands.map((b, i) => ({ ...b, i })).reverse();
  for (const b of order) {
    const half = (b.within + 0.5) * l.cellPx;
    const { px, py } = gridToPixel(l, target);
    const colour = b.i === 0 ? palette.bandBest : palette.band;
    ctx.strokeStyle = colour;
    ctx.lineWidth = (b.i === 0 ? 2.5 : 1.5) * scale;
    ctx.setLineDash(b.i === 0 ? [] : [6 * scale, 4 * scale]);
    ctx.strokeRect(px - half, py - half, half * 2, half * 2);
    ctx.setLineDash([]);
    // The label just above the square's top-left corner (clear of the star even for the
    // exact band), kept inside the plot.
    const lx = Math.max(l.left + 2, px - half);
    const ly = Math.max(l.top + 14 * scale, py - half - 2 * scale);
    const text = `${Number(b.points.toFixed(2))}`;
    ctx.lineWidth = 3 * scale;
    ctx.strokeStyle = palette.background;
    ctx.strokeText(text, lx, ly);
    ctx.fillStyle = b.i === 0 ? palette.bandBest : palette.bandLabel;
    ctx.fillText(text, lx, ly);
  }
  ctx.restore();
}

function drawDots(
  ctx: CanvasRenderingContext2D,
  l: PlotLayout,
  buckets: { p: GridPoint; count: number }[],
  palette: PlotPalette,
  scale: number,
) {
  // Area grows with the count (radius with its square root), capped so a crowd stays readable.
  const base = Math.max(3 * scale, l.cellPx * 0.22);
  const max = Math.max(base, l.cellPx * 0.9);
  ctx.font = `700 ${10 * scale}px system-ui, -apple-system, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (const { p, count } of [...buckets].sort((a, b) => b.count - a.count)) {
    const { px, py } = gridToPixel(l, p);
    const r = Math.min(max, base * Math.sqrt(count));
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.fillStyle = palette.dot;
    ctx.fill();
    ctx.globalAlpha = 1;
    if (count > 1 && r >= 7 * scale) {
      ctx.fillStyle = palette.dotLabel;
      ctx.fillText(String(count), px, py);
    }
  }
}

function drawStar(ctx: CanvasRenderingContext2D, l: PlotLayout, target: GridPoint, palette: PlotPalette, scale: number) {
  const { px, py } = gridToPixel(l, target);
  const outer = Math.max(7 * scale, Math.min(l.cellPx * 0.6, 16 * scale));
  const inner = outer * 0.45;
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const r = i % 2 === 0 ? outer : inner;
    const a = -Math.PI / 2 + (i * Math.PI) / 5;
    const x = px + r * Math.cos(a);
    const y = py + r * Math.sin(a);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fillStyle = palette.target;
  ctx.fill();
  ctx.lineWidth = 1.5 * scale;
  ctx.strokeStyle = palette.targetOutline;
  ctx.stroke();
}

/**
 * Every host view of the plot_point plane (docs/plans/t7-plot-the-point.md, P7): the plane with
 * its background image and overlays; with a distribution, one dot per answered grid point sized
 * by count; with an ACCURACY reveal, the target as a star and each band as a square around it,
 * labelled with its points. Fills its box with square cells and redraws on resize.
 */
export function PlotScatter({
  config, imageId, distribution, reveal, scale = 1, className = 'w-full h-full', onPick,
}: PlotScatterProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [layout, setLayout] = useState<PlotLayout | null>(null);
  // Bumped on every theme change, so the canvas redraws with the new token colours.
  const [themeVersion, setThemeVersion] = useState(0);

  useEffect(() => {
    const onThemeChange = () => setThemeVersion((v) => v + 1);
    window.addEventListener('themechange', onThemeChange);
    return () => window.removeEventListener('themechange', onThemeChange);
  }, []);

  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const measure = () => setSize({ width: box.clientWidth, height: box.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setImage(null);
    if (!imageId) return;
    const img = new Image();
    let live = true;
    img.onload = () => live && setImage(img);
    img.src = imageUrl(imageId);
    return () => {
      live = false;
    };
  }, [imageId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || size.width === 0 || size.height === 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(size.width * dpr);
    canvas.height = Math.round(size.height * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const l = plotLayoutFor(config, size.width, size.height, scale);
    const palette = plotPalette();
    drawPlane(ctx, config, l, palette, size.width, size.height, image, scale);
    setLayout(l);
    if (l.cellPx <= 0) return;
    const target = reveal ? graphToGrid(config, reveal.target) : null;
    if (target && reveal) drawBands(ctx, l, target, reveal.bands, palette, scale);
    if (distribution) drawDots(ctx, l, parseBuckets(distribution, config), palette, scale);
    if (target) drawStar(ctx, l, target, palette, scale);
  }, [config, size, image, distribution, reveal, scale, themeVersion]);

  const answers = distribution ? Object.values(distribution).reduce((a, b) => a + b, 0) : 0;
  const label =
    `Coordinate plane, x from ${formatCoord(config.xMin, config.xStep)} to ${formatCoord(config.xMax, config.xStep)}, ` +
    `y from ${formatCoord(config.yMin, config.yStep)} to ${formatCoord(config.yMax, config.yStep)}` +
    (distribution ? `, ${answers} ${answers === 1 ? 'answer' : 'answers'}` : '');

  return (
    <div
      ref={boxRef}
      className={`relative min-h-0 min-w-0 overflow-hidden ${className}`}
      style={size.width > 0 ? { maxHeight: plotHeightForWidth(config, size.width, scale) } : undefined}
    >
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={label}
        data-testid="plot-scatter"
        data-plot-left={layout?.left}
        data-plot-top={layout?.top}
        data-cell-px={layout?.cellPx}
        onClick={
          onPick
            ? (e) => {
                if (!layout || layout.cellPx <= 0) return;
                const rect = e.currentTarget.getBoundingClientRect();
                onPick(pixelToGrid(layout, { px: e.clientX - rect.left, py: e.clientY - rect.top }));
              }
            : undefined
        }
        style={{ width: size.width, height: size.height }}
        className={`absolute inset-0 block ${onPick ? 'cursor-crosshair' : ''}`}
      />
    </div>
  );
}
