/**
 * Puts errors where the user will look: a 422's problems next to the fields they belong to,
 * and anything else (a conflict, a server error, no connection) above the submit button.
 */
import { useState } from 'react';

import { ApiError, errorMessage } from '@/api/client';
import { formatCents } from '@/lib/formatCents';

export type FormErrors<K extends string> = {
  fields: Partial<Record<K, string>>;
  form: string | null;
};

export const NO_ERRORS: FormErrors<never> = { fields: {}, form: null };

/**
 * The backend reports a field by its dotted path: `amount_cents`, or for a pay schedule
 * `schedule.weekly.anchor_date`. A form names its fields its own way, so it passes a map from
 * the path's last part to its own field.
 */
export function formErrors<K extends string>(
  error: unknown,
  fieldFor: Readonly<Record<string, K>>,
): FormErrors<K> {
  if (!error) {
    return { fields: {}, form: null };
  }
  if (!(error instanceof ApiError) || Object.keys(error.fields).length === 0) {
    return { fields: {}, form: errorMessage(error) };
  }
  const fields: Partial<Record<K, string>> = {};
  const unplaced: string[] = [];
  for (const [path, problem] of Object.entries(error.fields)) {
    const name = path.split('.').at(-1) ?? path;
    const field = fieldFor[name];
    if (field && !fields[field]) {
      fields[field] = readable(name, problem);
    } else if (!field) {
      unplaced.push(path);
    }
  }
  const form = unplaced.length
    ? `Check these fields: ${unplaced.join(', ')}`
    : 'Check the fields marked above.';
  return { fields, form };
}

/**
 * The backend states money limits in cents, but the user types dollars: "less than or equal
 * to 100000000000" becomes "less than or equal to $1,000,000,000.00". Formatting only.
 */
function readable(name: string, problem: string): string {
  if (!name.endsWith('_cents')) {
    return problem;
  }
  return problem.replace(/\b(than|to) (-?\d+)$/, (_, word: string, cents: string) => {
    const value = Number(cents);
    return Number.isSafeInteger(value) ? `${word} ${formatCents(value)}` : `${word} ${cents}`;
  });
}

/** Errors the app finds before sending, such as an amount it can't read, win over the server's. */
export function mergeErrors<K extends string>(
  local: Partial<Record<K, string>>,
  server: FormErrors<K>,
): FormErrors<K> {
  return { fields: { ...server.fields, ...local }, form: server.form };
}

/** A form's values, with a setter per field: `set('name')(text)`. */
export function useFormValues<T extends object>(initial: T) {
  const [values, setValues] = useState(initial);
  const set =
    <K extends keyof T>(key: K) =>
    (value: T[K]) =>
      setValues((current) => ({ ...current, [key]: value }));
  return [values, set] as const;
}
