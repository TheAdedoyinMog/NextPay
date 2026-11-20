import {
  centsToText,
  hundredthsToText,
  parseHundredths,
  parseMoney,
  parseWholeNumber,
} from './money';

describe('parseHundredths', () => {
  it.each([
    ['0', 0],
    ['0.29', 29], // parseFloat('0.29') * 100 is 28.999999999999996
    ['19.99', 1999],
    ['1.1', 110],
    ['1.10', 110],
    ['0.07', 7],
    ['4.35', 435], // 4.35 * 100 is 434.99999999999994
    ['1250', 125000],
    ['1250.50', 125050],
    ['007.5', 750],
    ['-12.34', -1234],
    ['-0.5', -50],
    ['1000000000', 100000000000],
  ])('reads %p as %d', (text, expected) => {
    expect(parseHundredths(text)).toBe(expected);
  });

  it('never gives negative zero', () => {
    expect(Object.is(parseHundredths('-0'), 0)).toBe(true);
    expect(Object.is(parseHundredths('-0.00'), 0)).toBe(true);
  });

  it.each([
    '',
    '1.005', // three decimals: rejected, never rounded
    '0.001',
    '$5',
    '1,000',
    '1,000.00',
    ' 5',
    '5 ',
    '+5',
    '.5',
    '12.',
    '1e3',
    'NaN',
    'Infinity',
    '--5',
    '5-',
    '١٢', // non-ASCII digits
    '99999999999999999', // past the largest exact integer
  ])('rejects %p', (text) => {
    expect(parseHundredths(text)).toBeNull();
  });
});

describe('hundredthsToText', () => {
  it.each([
    [0, '0.00'],
    [7, '0.07'],
    [29, '0.29'],
    [1999, '19.99'],
    [125050, '1250.50'],
    [-50, '-0.50'],
    [-123456, '-1234.56'],
  ])('writes %d as %p', (hundredths, expected) => {
    expect(hundredthsToText(hundredths)).toBe(expected);
  });

  it('round-trips through parseHundredths', () => {
    for (const value of [0, 1, 29, 99, 100, 1999, 100000000000, -1, -2999]) {
      expect(parseHundredths(hundredthsToText(value))).toBe(value);
    }
  });

  it('refuses a non-integer, which would be a bug upstream', () => {
    expect(() => hundredthsToText(0.29)).toThrow(RangeError);
  });
});

describe('parseMoney', () => {
  it('returns cents', () => {
    expect(parseMoney('19.99')).toEqual({ ok: true, cents: 1999 });
    expect(centsToText(1999)).toBe('19.99');
  });

  it('asks for an amount when empty', () => {
    expect(parseMoney('')).toEqual({ ok: false, message: 'Enter an amount.' });
  });

  it('explains the format', () => {
    expect(parseMoney('1.005')).toEqual({
      ok: false,
      message: 'Use digits and an optional point, like 1250.50.',
    });
    expect(parseMoney('$5').ok).toBe(false);
  });

  it('allows a minus only when asked', () => {
    expect(parseMoney('-20')).toEqual({
      ok: false,
      message: 'Enter an amount without a minus sign.',
    });
    expect(parseMoney('-20', { allowNegative: true })).toEqual({ ok: true, cents: -2000 });
  });
});

describe('parseWholeNumber', () => {
  it.each([
    ['1', 1],
    ['15', 15],
    ['007', 7],
  ])('reads %p', (text, expected) => {
    expect(parseWholeNumber(text)).toBe(expected);
  });

  it.each(['', '1.5', '-1', ' 1', '1e2', 'x'])('rejects %p', (text) => {
    expect(parseWholeNumber(text)).toBeNull();
  });
});
