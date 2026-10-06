import { describe, expect, it } from 'vitest';
import {
  cellDistance,
  evaluatePolynomial,
  formatCoord,
  formatGridPoint,
  graphToGrid,
  graphToPixel,
  gridSize,
  gridToGraph,
  gridToPixel,
  inPlane,
  layoutPlot,
  lineCrossings,
  pixelToGrid,
  polynomialPaths,
  roundToStep,
  snapIndex,
  stepDecimals,
  type PlotConfig,
} from './plotGeometry';

const PLANE: PlotConfig = { xMin: -10, xMax: 10, xStep: 1, yMin: -10, yMax: 10, yStep: 1 };
const NO_MARGIN = { left: 0, right: 0, top: 0, bottom: 0 };
const MINUS = '−';

describe('gridSize', () => {
  it('rounds like the server, never floors', () => {
    expect(gridSize(PLANE)).toEqual({ nCols: 20, nRows: 20 });
    // (2 - 0) / 0.1 is 20.000000000000004 and (0.7 - 0) / 0.1 is 6.999999999999999
    expect(gridSize({ ...PLANE, xMin: 0, xMax: 2, xStep: 0.1, yMin: 0, yMax: 0.7, yStep: 0.1 })).toEqual({
      nCols: 20,
      nRows: 7,
    });
  });

  it('handles decimal and large steps', () => {
    expect(gridSize({ ...PLANE, xMin: 0, xMax: 5, xStep: 0.5, yMin: 0, yMax: 100, yStep: 5 })).toEqual({
      nCols: 10,
      nRows: 20,
    });
    expect(gridSize({ ...PLANE, xMin: -20, xMax: 20, xStep: 2 }).nCols).toBe(20);
  });
});

describe('stepDecimals', () => {
  it.each([
    [1, 0], [2, 0], [5, 0], [500000, 0],
    [0.5, 1], [0.2, 1], [0.1, 1],
    [0.05, 2], [0.001, 3],
  ])('step %s has %s decimals', (step, decimals) => {
    expect(stepDecimals(step)).toBe(decimals);
  });
});

describe('roundToStep and formatCoord', () => {
  it('removes float noise and returns plain numbers', () => {
    expect(roundToStep(0.1 * 3, 0.1)).toBe(0.3);
    expect(roundToStep(-2, 1)).toBe(-2);
    expect(roundToStep(-0.0000001, 0.1)).toBe(0); // never -0
    expect(Object.is(roundToStep(-0.0000001, 0.1), -0)).toBe(false);
    expect(roundToStep(2.5, 0.5)).toBe(2.5);
    expect(roundToStep(0.123, 0.05)).toBe(0.12);
  });

  it('formats with a typographic minus and the step decimals', () => {
    expect(formatCoord(-2, 1)).toBe(`${MINUS}2`);
    expect(formatCoord(3, 1)).toBe('3');
    expect(formatCoord(0.1 * 3, 0.1)).toBe('0.3');
    expect(formatCoord(-0.05, 0.05)).toBe(`${MINUS}0.05`);
    expect(formatCoord(2, 0.5)).toBe('2'); // no trailing zeros
    expect(formatGridPoint(PLANE, { col: 13, row: 8 })).toBe(`(3, ${MINUS}2)`);
  });
});

describe('grid <-> graph units', () => {
  it('converts both ways', () => {
    expect(gridToGraph(PLANE, { col: 13, row: 8 })).toEqual({ x: 3, y: -2 });
    expect(gridToGraph(PLANE, { col: 0, row: 0 })).toEqual({ x: -10, y: -10 });
    expect(graphToGrid(PLANE, { x: 3, y: -2 })).toEqual({ col: 13, row: 8 });
  });

  it('works on decimal grids without float noise', () => {
    const fine: PlotConfig = { ...PLANE, xMin: 0, xMax: 2, xStep: 0.1, yMin: 0, yMax: 2, yStep: 0.1 };
    expect(gridToGraph(fine, { col: 3, row: 7 })).toEqual({ x: 0.3, y: 0.7 });
    expect(graphToGrid(fine, { x: 0.30000000000000004, y: 0.7 })).toEqual({ col: 3, row: 7 });
  });

  it('snaps typed values to the nearest grid point and clamps to the plane', () => {
    expect(graphToGrid(PLANE, { x: 3.4, y: -2.6 })).toEqual({ col: 13, row: 7 });
    expect(graphToGrid(PLANE, { x: 99, y: -99 })).toEqual({ col: 20, row: 0 });
  });

  it('rounds a value exactly midway UP', () => {
    expect(snapIndex(2.5, 20)).toBe(3);
    expect(snapIndex(-0.5, 20)).toBe(0);
    expect(graphToGrid(PLANE, { x: 2.5, y: -2.5 })).toEqual({ col: 13, row: 8 });
  });

  it('measures cell distance as max(|dcol|, |drow|)', () => {
    expect(cellDistance({ col: 13, row: 8 }, { col: 14, row: 9 })).toBe(1);
    expect(cellDistance({ col: 13, row: 8 }, { col: 8, row: 13 })).toBe(5);
    expect(cellDistance({ col: 0, row: 0 }, { col: 0, row: 0 })).toBe(0);
  });

  it('knows what is inside the plane', () => {
    expect(inPlane(PLANE, { x: 10, y: -10 })).toBe(true);
    expect(inPlane(PLANE, { x: 10.5, y: 0 })).toBe(false);
  });
});

describe('layout and pixels', () => {
  it('fits square cells and centres horizontally', () => {
    const l = layoutPlot(PLANE, 300, 200, NO_MARGIN);
    expect(l.cellPx).toBe(10); // limited by height: 200 / 20
    expect(l.width).toBe(200);
    expect(l.height).toBe(200);
    expect(l.left).toBe(50); // (300 - 200) / 2
    expect(l.top).toBe(0);
  });

  it('keeps cells square on unequal grids', () => {
    const wide: PlotConfig = { ...PLANE, yMin: 0, yMax: 5 }; // 20 x 5 cells
    const l = layoutPlot(wide, 400, 400, { left: 20, right: 0, top: 10, bottom: 10 });
    expect(l.cellPx).toBe(19); // (400 - 20) / 20
    expect(l.height).toBe(95);
  });

  it('flips y: the top-left pixel is (xMin, yMax)', () => {
    const l = layoutPlot(PLANE, 200, 200, NO_MARGIN);
    expect(gridToPixel(l, { col: 0, row: 20 })).toEqual({ px: 0, py: 0 });
    expect(pixelToGrid(l, { px: 0, py: 0 })).toEqual({ col: 0, row: 20 });
    expect(gridToGraph(PLANE, pixelToGrid(l, { px: 0, py: 0 }))).toEqual({ x: -10, y: 10 });
    expect(gridToPixel(l, { col: 0, row: 0 })).toEqual({ px: 0, py: 200 });
    expect(gridToPixel(l, { col: 13, row: 8 })).toEqual({ px: 130, py: 120 });
  });

  it('snaps a pixel to the nearest grid point and clamps outside taps', () => {
    const l = layoutPlot(PLANE, 200, 200, NO_MARGIN);
    expect(pixelToGrid(l, { px: 133, py: 117 })).toEqual({ col: 13, row: 8 });
    expect(pixelToGrid(l, { px: 135, py: 125 })).toEqual({ col: 14, row: 8 }); // midway rounds up
    expect(pixelToGrid(l, { px: -50, py: 500 })).toEqual({ col: 0, row: 0 });
    expect(pixelToGrid(l, { px: 999, py: -999 })).toEqual({ col: 20, row: 20 });
  });

  it('round-trips every grid point through pixels', () => {
    const l = layoutPlot(PLANE, 347, 211, { left: 30, right: 5, top: 8, bottom: 24 });
    for (let col = 0; col <= 20; col++) {
      for (let row = 0; row <= 20; row++) {
        expect(pixelToGrid(l, gridToPixel(l, { col, row }))).toEqual({ col, row });
      }
    }
  });

  it('places any graph point in pixels', () => {
    const l = layoutPlot(PLANE, 200, 200, NO_MARGIN);
    expect(graphToPixel(PLANE, l, { x: 0.5, y: 0.5 })).toEqual({ px: 105, py: 95 });
  });
});

describe('lineCrossings', () => {
  const near = (p: { x: number; y: number }, x: number, y: number) => {
    expect(p.x).toBeCloseTo(x, 9);
    expect(p.y).toBeCloseTo(y, 9);
  };

  it('extends a sloped line to the plane edges', () => {
    const hit = lineCrossings(PLANE, { x1: 0, y1: 1, x2: 1, y2: 3 })!; // y = 2x + 1
    near(hit[0], -5.5, -10);
    near(hit[1], 4.5, 10);
  });

  it('handles vertical and horizontal lines', () => {
    const v = lineCrossings(PLANE, { x1: 2, y1: 0, x2: 2, y2: 1 })!;
    near(v[0], 2, -10);
    near(v[1], 2, 10);
    const h = lineCrossings(PLANE, { x1: 0, y1: -3, x2: 5, y2: -3 })!;
    near(h[0], -10, -3);
    near(h[1], 10, -3);
  });

  it('returns null for a line that misses the plane', () => {
    expect(lineCrossings(PLANE, { x1: 20, y1: 0, x2: 20, y2: 1 })).toBeNull();
    expect(lineCrossings(PLANE, { x1: 0, y1: 50, x2: 1, y2: 50 })).toBeNull();
    expect(lineCrossings(PLANE, { x1: 0, y1: 30, x2: 1, y2: 31 })).toBeNull(); // y = x + 30
    expect(lineCrossings(PLANE, { x1: 1, y1: 1, x2: 1, y2: 1 })).toBeNull(); // not a line
  });
});

describe('polynomials', () => {
  it('evaluates c0 + c1 x + c2 x^2 + c3 x^3', () => {
    expect(evaluatePolynomial([-3, -2, 1], 1)).toBe(-4); // vertex of x^2 - 2x - 3
    expect(evaluatePolynomial([0, 0, 0, 1], -2)).toBe(-8);
    expect(evaluatePolynomial([7], 123)).toBe(7);
  });

  it('clips curves to the plane and breaks them where they leave', () => {
    const l = layoutPlot(PLANE, 200, 200, NO_MARGIN);
    const inBounds = (paths: { px: number; py: number }[][]) =>
      paths.every((path) =>
        path.every((p) => p.px >= -1e-9 && p.px <= 200 + 1e-9 && p.py >= -1e-9 && p.py <= 200 + 1e-9),
      );

    // x^2 - 2x - 3 leaves through the top on both sides: one piece, ends on the top edge.
    const parabola = polynomialPaths(PLANE, l, [-3, -2, 1]);
    expect(parabola).toHaveLength(1);
    expect(inBounds(parabola)).toBe(true);
    expect(parabola[0][0].py).toBeCloseTo(0, 6);
    expect(parabola[0][parabola[0].length - 1].py).toBeCloseTo(0, 6);

    // x^3 - 9x leaves and re-enters: still drawn, never outside the plane.
    const cubic = polynomialPaths(PLANE, l, [0, -9, 0, 1]);
    expect(cubic.length).toBeGreaterThanOrEqual(1);
    expect(inBounds(cubic)).toBe(true);

    // A curve entirely above the plane draws nothing.
    expect(polynomialPaths(PLANE, l, [50])).toEqual([]);
  });

  it('breaks a curve into separate pieces when it leaves and comes back', () => {
    // y = 20 - x^2 is above the plane between about -3.16 and 3.16 and inside on both sides.
    const l = layoutPlot(PLANE, 200, 200, NO_MARGIN);
    expect(polynomialPaths(PLANE, l, [20, 0, -1])).toHaveLength(2);
  });
});
