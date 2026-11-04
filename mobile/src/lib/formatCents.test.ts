import { formatCents } from './formatCents';

describe('formatCents', () => {
  it.each([
    [0, '$0.00'],
    [-0, '$0.00'],
    [1, '$0.01'],
    [10, '$0.10'],
    [99, '$0.99'],
    [100, '$1.00'],
    [123456, '$1,234.56'],
    [100000, '$1,000.00'],
    [99999, '$999.99'],
    [100000000, '$1,000,000.00'],
    [100000000000, '$1,000,000,000.00'],
    [Number.MAX_SAFE_INTEGER, '$90,071,992,547,409.91'],
  ])('formats %d as %s', (cents, expected) => {
    expect(formatCents(cents)).toBe(expected);
  });

  it.each([
    [-1, '-$0.01'],
    [-99, '-$0.99'],
    [-100, '-$1.00'],
    [-123456, '-$1,234.56'],
    [-100000000, '-$1,000,000.00'],
  ])('puts the sign before the dollar sign: %d as %s', (cents, expected) => {
    expect(formatCents(cents)).toBe(expected);
  });

  it.each([[12.5], [0.1], [NaN], [Infinity], [2 ** 53]])('refuses %d', (cents) => {
    expect(() => formatCents(cents)).toThrow(RangeError);
  });
});
