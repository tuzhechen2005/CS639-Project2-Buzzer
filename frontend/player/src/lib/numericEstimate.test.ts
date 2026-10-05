import { describe, expect, it } from 'vitest';
import {
  bandLabel, differenceLine, formatNumber, landedBandIndex, numericVerdict, outcomeLine, type NumericReveal,
} from './numericEstimate';

const relative: NumericReveal = {
  type: 'numeric_estimate', target: 1665, mode: 'relative',
  bands: [{ within: 5, points: 100 }, { within: 15, points: 50 }, { within: 30, points: 25 }],
};
const absolute: NumericReveal = {
  type: 'numeric_estimate', target: 1789, mode: 'absolute',
  bands: [{ within: 1, points: 10 }, { within: 5, points: 4 }],
};

describe('formatNumber', () => {
  it('groups thousands and hides floating-point noise', () => {
    expect(formatNumber(1665)).toBe('1,665');
    expect(formatNumber(1.665)).toBe('1.665');
    expect(formatNumber(0.1 + 0.2)).toBe('0.3');
    expect(formatNumber(35)).toBe('35');
    expect(formatNumber(-0)).toBe('0');
  });
});

describe('result lines', () => {
  it('matches the awarded points to a band, never recomputing from the value', () => {
    expect(landedBandIndex(relative, 100)).toBe(0);
    expect(landedBandIndex(relative, 50)).toBe(1);
    expect(landedBandIndex(relative, 0)).toBeNull();
    expect(outcomeLine(relative, 100)).toBe('Within 5 %');
    expect(outcomeLine(relative, 25)).toBe('Within 30 %');
    expect(outcomeLine(relative, 0)).toBe('More than 30 % off');
    expect(outcomeLine(absolute, 4, 'years')).toBe('Within ±5 years');
    expect(outcomeLine(absolute, 0, 'years')).toBe('More than 5 years off');
  });

  it('labels bands and differences', () => {
    expect(bandLabel(relative, 15)).toBe('Within 15 %');
    expect(bandLabel(absolute, 1)).toBe('Within ±1');
    expect(differenceLine(1700, 1665, 'steps')).toBe('35 steps off');
    expect(differenceLine(1600, 1665)).toBe('65 off');
    expect(differenceLine(1.5, 1.2)).toBe('0.3 off');
  });

  it('classifies correct, close and incorrect from points', () => {
    expect(numericVerdict(relative, 100)).toBe('correct');
    expect(numericVerdict(relative, 50)).toBe('close');
    expect(numericVerdict(relative, 0)).toBe('incorrect');
  });
});
