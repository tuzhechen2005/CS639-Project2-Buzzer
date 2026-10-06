import { useEffect, useRef, useState } from 'react';
import { imageUrl } from '../lib/images';
import { drawPlane, drawPlayerPoint, planeDescription, plotHeightForWidth, plotLayoutFor } from '../lib/plotDraw';
import { pixelToGrid, type GridPoint, type PlotConfig, type PlotLayout } from '../lib/plotGeometry';
import { plotPalette } from '../lib/plotPalette';

interface PlotCanvasProps {
  config: PlotConfig;
  /** config.image_id: the plane's background (T8). Loads in the background, never blocks. */
  imageId?: string | null;
  point: GridPoint | null;
  /** Called with the snapped grid point on pointer-down and while dragging. */
  onPoint: (p: GridPoint) => void;
  /** Locked or submitted: input is ignored and a drag in progress ends where the point is. */
  disabled: boolean;
  /** Sizes the box (it is the flex item; its height is capped at what the plane needs). */
  className?: string;
}

/**
 * The plot_point plane (docs/plans/t7-plot-the-point.md, P6). It fills its parent, keeps the
 * cells square, draws at devicePixelRatio and redraws on resize and rotation. The first active
 * pointer places and drags the point, snapping live; other pointers are ignored until it lifts.
 * The plot rectangle is exposed as data-plot-left / data-plot-top / data-cell-px (CSS px) for the
 * browser test.
 */
export function PlotCanvas({ config, imageId, point, onPoint, disabled, className = 'h-full w-full' }: PlotCanvasProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pointerRef = useRef<number | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [layout, setLayout] = useState<PlotLayout | null>(null);

  // Size follows the parent box (resize and rotation both change it).
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const measure = () => setSize({ width: box.clientWidth, height: box.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  // The background image: the grid draws at once and again when the image arrives; a failure
  // leaves the plane without it, with no message.
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
    const l = plotLayoutFor(config, size.width, size.height);
    const palette = plotPalette();
    drawPlane(ctx, config, l, palette, size.width, size.height, image);
    if (point) drawPlayerPoint(ctx, l, point, palette);
    setLayout(l);
  }, [config, size, image, point]);

  // Locking ends a drag in progress; the point stays where it is.
  useEffect(() => {
    if (!disabled || pointerRef.current === null) return;
    const canvas = canvasRef.current;
    if (canvas?.hasPointerCapture(pointerRef.current)) canvas.releasePointerCapture(pointerRef.current);
    pointerRef.current = null;
  }, [disabled]);

  function pointAt(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!layout) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const p = pixelToGrid(layout, { px: e.clientX - rect.left, py: e.clientY - rect.top });
    if (!point || p.col !== point.col || p.row !== point.row) onPoint(p);
  }

  function onPointerDown(e: React.PointerEvent<HTMLCanvasElement>) {
    if (disabled || pointerRef.current !== null) return;
    e.preventDefault();
    pointerRef.current = e.pointerId;
    e.currentTarget.setPointerCapture(e.pointerId);
    pointAt(e);
  }

  function onPointerMove(e: React.PointerEvent<HTMLCanvasElement>) {
    if (disabled || e.pointerId !== pointerRef.current) return;
    pointAt(e);
  }

  function onPointerEnd(e: React.PointerEvent<HTMLCanvasElement>) {
    if (e.pointerId !== pointerRef.current) return;
    pointerRef.current = null;
  }

  return (
    // No taller than the plane needs at this width, so the controls sit right below it.
    <div
      ref={boxRef}
      className={`relative min-h-0 min-w-0 overflow-hidden ${className}`}
      style={size.width > 0 ? { maxHeight: plotHeightForWidth(config, size.width) } : undefined}
    >
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={planeDescription(config)}
        data-plot-left={layout?.left}
        data-plot-top={layout?.top}
        data-cell-px={layout?.cellPx}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerEnd}
        onPointerCancel={onPointerEnd}
        onLostPointerCapture={onPointerEnd}
        style={{ width: size.width, height: size.height, touchAction: 'none' }}
        className={`absolute inset-0 block select-none ${disabled ? 'cursor-not-allowed' : 'cursor-crosshair'}`}
      />
    </div>
  );
}
