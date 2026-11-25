/**
 * A stand-in for expo-apple-authentication, mocked for every test in jest.setup.js. It
 * behaves like Apple where the app depends on it:
 *
 * - The identity token carries the nonce the app passed (which should be a hash), so the fake
 *   backend can check the raw nonce against it as the real backend does.
 * - The name and email come only on the first sign-in for each Apple ID; later ones get null.
 *
 * Tokens look like `apple-identity|<apple user id>|<nonce given to Apple>`.
 */
import { createElement } from 'react';
import { Pressable, Text } from 'react-native';

export const AppleAuthenticationScope = { FULL_NAME: 0, EMAIL: 1 } as const;
export const AppleAuthenticationButtonType = { SIGN_IN: 0, CONTINUE: 1, SIGN_UP: 2 } as const;
export const AppleAuthenticationButtonStyle = { WHITE: 0, WHITE_OUTLINE: 1, BLACK: 2 } as const;

type FullName = { givenName: string | null; familyName: string | null };

/** Who is signed in to iCloud on this fake phone. */
export const appleId = {
  user: '001234.ada',
  fullName: { givenName: 'Ada', familyName: 'Lovelace' } as FullName,
  email: 'x7k2p9@privaterelay.appleid.com',
};

/** Apple IDs that have already authorized NextPay: Apple won't share their name again. */
export const authorized = new Set<string>();

/** What the next signInAsync does instead of succeeding. */
export const next: { outcome: 'success' | 'cancel' | 'fail' | 'noToken' } = {
  outcome: 'success',
};

export const isAvailableAsync = jest.fn(async () => true);

export const signInAsync = jest.fn(async (options: { nonce?: string } = {}) => {
  const outcome = next.outcome;
  next.outcome = 'success';
  if (outcome === 'cancel') {
    throw Object.assign(new Error('The user canceled the authorization attempt'), {
      code: 'ERR_REQUEST_CANCELED',
    });
  }
  if (outcome === 'fail') {
    throw Object.assign(new Error('The authorization attempt failed'), {
      code: 'ERR_REQUEST_UNKNOWN',
    });
  }
  const isFirst = !authorized.has(appleId.user);
  authorized.add(appleId.user);
  return {
    user: appleId.user,
    state: null,
    authorizationCode: 'code',
    identityToken:
      outcome === 'noToken' ? null : `apple-identity|${appleId.user}|${options.nonce ?? ''}`,
    fullName: isFirst ? { ...appleId.fullName } : null,
    email: isFirst ? appleId.email : null,
    realUserStatus: 1,
  };
});

export function formatFullName(name: FullName): string {
  return [name.givenName, name.familyName].filter(Boolean).join(' ');
}

export function AppleAuthenticationButton({ onPress }: { onPress: () => void }) {
  return createElement(
    Pressable,
    { accessibilityRole: 'button', accessibilityLabel: 'Sign in with Apple', onPress },
    createElement(Text, null, 'Sign in with Apple'),
  );
}

export function reset(): void {
  authorized.clear();
  next.outcome = 'success';
  isAvailableAsync.mockClear();
  signInAsync.mockClear();
}
