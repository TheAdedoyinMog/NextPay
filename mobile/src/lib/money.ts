/**
 * Converting between what a person types and integer cents. Parsing works on the text, never
 * on a float: `parseFloat('0.29') * 100` is 28.999999999999996 (ADR 0001, ADR 0012).
 *
 * The rules match the engine's `Money.parse`: an optional minus, ASCII digits, then optionally
 * a point and one or two digits. Everything else is rejected: "$", commas, spaces, a plus,
 * ".5", "12.", and three or more decimals. Parsing never rounds.
 */

// The engine's pattern (engine/src/nextpay_engine/money.py), anchored at both ends.
const DECIMAL_PATTERN = /^(-?)([0-9]+)(?:\.([0-9]{1,2}))?$/;

/** Text with up to two decimals, as an integer number of hundredths; null if it isn't one. */
export function parseHundredths(text: string): number | null {
  const match = DECIMAL_PATTERN.exec(text);
  if (!match) {
    return null;
  }
  const [, sign, whole = '', fraction = ''] = match;
  // Join the digits: "0" and "29" make "029", which is 29. No multiplication, no float.
  const hundredths = Number(whole + fraction.padEnd(2, '0'));
  if (!Number.isSafeInteger(hundredths)) {
    return null;
  }
  return sign && hundredths !== 0 ? -hundredths : hundredths;
}

/** Integer hundredths as editable text, the inverse of `parseHundredths`: 2999 is "29.99". */
export function hundredthsToText(hundredths: number): string {
  if (!Number.isSafeInteger(hundredths)) {
    throw new RangeError(`hundredthsToText needs an integer, got ${hundredths}`);
  }
  const digits = String(Math.abs(hundredths)).padStart(3, '0');
  return `${hundredths < 0 ? '-' : ''}${digits.slice(0, -2)}.${digits.slice(-2)}`;
}

export type MoneyParse = { ok: true; cents: number } | { ok: false; message: string };

/** What the user typed in a money field, as cents, or why it can't be read. */
export function parseMoney(text: string, options: { allowNegative?: boolean } = {}): MoneyParse {
  if (text === '') {
    return { ok: false, message: 'Enter an amount.' };
  }
  const cents = parseHundredths(text);
  if (cents === null) {
    return { ok: false, message: 'Use digits and an optional point, like 1250.50.' };
  }
  if (cents < 0 && !options.allowNegative) {
    return { ok: false, message: 'Enter an amount without a minus sign.' };
  }
  return { ok: true, cents };
}

/** Cents as the text a money field starts with when editing: 125050 is "1250.50". */
export const centsToText = hundredthsToText;

/** A whole number such as a priority or a day of the month, typed as digits only. */
export function parseWholeNumber(text: string): number | null {
  if (!/^[0-9]+$/.test(text)) {
    return null;
  }
  const value = Number(text);
  return Number.isSafeInteger(value) ? value : null;
}
