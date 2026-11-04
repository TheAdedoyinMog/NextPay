/**
 * The only money code in the app: turns integer cents into display text.
 * Works on the digits and never divides, so no float is involved (ADR 0012).
 */
export function formatCents(cents: number): string {
  if (!Number.isSafeInteger(cents)) {
    throw new RangeError(`formatCents needs an integer number of cents, got ${cents}`);
  }
  const digits = String(Math.abs(cents)).padStart(3, '0');
  const dollars = digits.slice(0, -2).replace(/\B(?=(\d{3})+$)/g, ',');
  return `${cents < 0 ? '-' : ''}$${dollars}.${digits.slice(-2)}`;
}
