import { describe, expect, it } from 'vitest';
import type { PlotConfig } from './plotGeometry';
import {
  EMPTY_TYPED,
  canSubmitTyped,
  commitAxis,
  commitForSubmit,
  distanceText,
  flipSign,
  gridPointOf,
  placedOnCanvas,
  plotConfigOf,
  plotResultLine,
  plotVerdict,
  type PlotReveal,
} from './plotPoint';

const PLANE: PlotConfig = { xMin: -10, xMax: 10, xStep: 1, yMin: -10, yMax: 10, yStep: 1 };
const MINUS = '−';
const REVEAL: PlotReveal = {
  type: 'plot_point',
  target: { x: 3, y: -2 },
  bands: [
    { within: 0, points: 100 },
    { within: 1, points: 50 },
  ],
};

describe('plotConfigOf and gridPointOf', () => {
  it('needs all six numbers', () => {
    expect(plotConfigOf({ ...PLANE })).toMatchObject(PLANE);
    expect(plotConfigOf({ xMin: -10, xMax: 10, xStep: 1 })).toBeNull();
    expect(plotConfigOf(undefined)).toBeNull();
  });

  it('reads {col, row} integers only', () => {
    expect(gridPointOf({ col: 13, row: 8 })).toEqual({ col: 13, row: 8 });
    expect(gridPointOf({ col: 1.5, row: 8 })).toBeNull();
    expect(gridPointOf(null)).toBeNull();
  });
});

describe('typed coordinates', () => {
  it('places nothing until both fields parse, then snaps and clamps', () => {
    const one = commitAxis(PLANE, { ...EMPTY_TYPED, xText: '3' }, 'x');
    expect(one.point).toBeNull();
    expect(one.xText).toBe('3'); // stays as typed
    expect(one.needBoth).toBe(true);

    const both = commitAxis(PLANE, { ...one, yText: `${MINUS}2.4` }, 'y');
    expect(both.point).toEqual({ col: 13, row: 8 });
    expect(both).toMatchObject({ xText: '3', yText: `${MINUS}2`, needBoth: false });

    const clamped = commitAxis(PLANE, { ...EMPTY_TYPED, xText: '99', yText: '-99' }, 'y');
    expect(clamped).toMatchObject({ point: { col: 20, row: 0 }, xText: '10', yText: `${MINUS}10` });
  });

  it('moves only the committed axis when a point exists', () => {
    const s = { ...placedOnCanvas(PLANE, { col: 13, row: 8 }), xText: '5', yText: '7' };
    const next = commitAxis(PLANE, s, 'x');
    expect(next.point).toEqual({ col: 15, row: 8 });
    expect(next.xText).toBe('5');
    expect(next.yText).toBe('7'); // pending text in the other field is not committed
  });

  it('reverts rejected text to the point when one exists', () => {
    const s = { ...placedOnCanvas(PLANE, { col: 13, row: 8 }), xText: 'abc' };
    const next = commitAxis(PLANE, s, 'x');
    expect(next.point).toEqual({ col: 13, row: 8 });
    expect(next.xText).toBe('3');
  });

  it('commits both fields on Submit and judges Submit on the live text', () => {
    const s = { ...EMPTY_TYPED, xText: '3', yText: '-2' };
    expect(canSubmitTyped(s)).toBe(true);
    expect(commitForSubmit(PLANE, s).point).toEqual({ col: 13, row: 8 });
    expect(canSubmitTyped({ ...EMPTY_TYPED, xText: '3' })).toBe(false);
    expect(canSubmitTyped({ ...EMPTY_TYPED, xText: '3', yText: 'x' })).toBe(false);
    expect(canSubmitTyped(placedOnCanvas(PLANE, { col: 0, row: 0 }))).toBe(true);
    expect(commitForSubmit(PLANE, { ...EMPTY_TYPED, xText: '3' }).point).toBeNull();
  });

  it('flips the sign with a typographic minus; an empty field gets "−"', () => {
    expect(flipSign('')).toBe(MINUS);
    expect(flipSign('3')).toBe(`${MINUS}3`);
    expect(flipSign(`${MINUS}3`)).toBe('3');
    expect(flipSign('-3')).toBe('3');
  });

  it('follows the canvas in both fields', () => {
    const fine: PlotConfig = { ...PLANE, xMin: 0, xMax: 2, xStep: 0.1, yMin: 0, yMax: 2, yStep: 0.1 };
    expect(placedOnCanvas(fine, { col: 3, row: 7 })).toMatchObject({ xText: '0.3', yText: '0.7' });
  });
});

describe('result text', () => {
  it('reads the distance', () => {
    expect(distanceText(0)).toBe('Exact');
    expect(distanceText(1)).toBe('1 cell off');
    expect(distanceText(4)).toBe('4 cells off');
  });

  it('writes one line for an answer, a miss, no answer and COMPLETENESS', () => {
    expect(plotResultLine(PLANE, REVEAL, { col: 14, row: 8 }, 50)).toBe(
      `You: (4, ${MINUS}2) · Target: (3, ${MINUS}2) · 1 cell off · 50 pts`,
    );
    expect(plotResultLine(PLANE, REVEAL, { col: 13, row: 8 }, 100)).toContain('Exact · 100 pts');
    expect(plotResultLine(PLANE, REVEAL, { col: 17, row: 8 }, 0)).toContain('4 cells off · 0 pts');
    expect(plotResultLine(PLANE, REVEAL, null, 0)).toBe(`Target: (3, ${MINUS}2)`);
    expect(plotResultLine(PLANE, null, { col: 14, row: 8 }, 0)).toBe(`Answer recorded: (4, ${MINUS}2)`);
  });

  it('calls the first band correct, other points close, zero incorrect', () => {
    expect(plotVerdict(REVEAL, 100)).toBe('correct');
    expect(plotVerdict(REVEAL, 50)).toBe('close');
    expect(plotVerdict(REVEAL, 0)).toBe('incorrect');
  });
});
