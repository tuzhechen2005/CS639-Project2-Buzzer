import { describe, expect, it } from 'vitest';
import { parseNumber } from './parseNumber';

describe('parseNumber', () => {
  const accepted: [string, number][] = [
    ['1665', 1665],
    ['1665.5', 1665.5],
    ['.5', 0.5],
    ['5.', 5],
    ['-12', -12],
    ['-.5', -0.5],
    ['-0', 0],
    ['007', 7],
    ['1,665', 1665],
    ['1,665,000', 1665000],
    ['1,665.5', 1665.5],
    ['0,500', 500],
    ['1,5', 1.5],
    ['1,66', 1.66],
    ['0,5', 0.5],
    ['  42  ', 42],
    ['-1,665', -1665],
    ['1000000000000000', 1e15],
  ];
  it.each(accepted)('accepts %s', (text, value) => {
    expect(parseNumber(text)).toBe(value);
  });

  const rejected = [
    '', '   ', '-', '.', '-.', '+5', '1,000.', '1665,000', '12345,678', '1,6650', '1,66.5', '1.665,5',
    '1,2,3', '1 665', '1e3', '١٢٣', '−5', '1665 steps', '1000000000000001', 'abc', '--5', '5-', '1..5',
    '9'.repeat(400),
  ];
  it.each(rejected)('rejects %j', (text) => {
    expect(parseNumber(text)).toBeNull();
  });

  it('never returns negative zero', () => {
    expect(Object.is(parseNumber('-0'), 0)).toBe(true);
    expect(Object.is(parseNumber('-0.0'), 0)).toBe(true);
  });
});
