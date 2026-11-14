/**
 * An in-memory stand-in for expo-secure-store. Use it with
 * `jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));`
 * and import this module in the test to look inside.
 */
export const items = new Map<string, string>();

export const WHEN_UNLOCKED_THIS_DEVICE_ONLY = 6;

export const getItemAsync = jest.fn(async (key: string) => items.get(key) ?? null);

export const setItemAsync = jest.fn(async (key: string, value: string) => {
  items.set(key, value);
});

export const deleteItemAsync = jest.fn(async (key: string) => {
  items.delete(key);
});

export const REFRESH_TOKEN_KEY = 'nextpay.refresh_token';

export function reset(): void {
  items.clear();
  getItemAsync.mockClear();
  setItemAsync.mockClear();
  deleteItemAsync.mockClear();
}
