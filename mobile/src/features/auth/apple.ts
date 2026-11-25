/**
 * Sign in with Apple (ADR 0019). Apple signs the user in on the phone and hands us an identity
 * token, which the backend verifies and swaps for the same tokens as email/password.
 *
 * The nonce: each attempt makes 32 random bytes, gives Apple their SHA-256, and sends the raw
 * value to the backend, which hashes it and compares it with the token. The raw value is in no
 * token, so a leaked token can't be replayed on its own.
 */
import { useMutation } from '@tanstack/react-query';
import * as AppleAuthentication from 'expo-apple-authentication';
import * as Crypto from 'expo-crypto';

import { api, unwrap } from '@/api/client';
import { session } from '@/api/session';

/** Apple itself failed, before our backend was asked. */
export class AppleSignInError extends Error {
  constructor() {
    super(
      "Sign in with Apple didn't work. Check that you're signed in to iCloud in Settings, then try again.",
    );
    this.name = 'AppleSignInError';
  }
}

export type AppleSignInResult = 'signedIn' | 'canceled';

function makeNonce(): string {
  return Array.from(Crypto.getRandomBytes(32), (byte) => byte.toString(16).padStart(2, '0')).join(
    '',
  );
}

function isCanceled(error: unknown): boolean {
  return (error as { code?: unknown } | null)?.code === 'ERR_REQUEST_CANCELED';
}

/**
 * Signs in with Apple. Resolves 'canceled' when the user closes Apple's sheet: that's a choice,
 * not an error. Rejects with an AppleSignInError, or the backend's ApiError.
 */
export function useAppleSignIn() {
  return useMutation({
    mutationFn: async (): Promise<AppleSignInResult> => {
      const nonce = makeNonce();
      let credential: AppleAuthentication.AppleAuthenticationCredential;
      try {
        credential = await AppleAuthentication.signInAsync({
          requestedScopes: [
            AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
            AppleAuthentication.AppleAuthenticationScope.EMAIL,
          ],
          nonce: await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, nonce),
        });
      } catch (error) {
        if (isCanceled(error)) {
          return 'canceled';
        }
        throw new AppleSignInError();
      }
      if (!credential.identityToken) {
        throw new AppleSignInError();
      }
      // Apple shares the name only the first time. Later it's null, and the backend keeps the
      // first one.
      const fullName = credential.fullName
        ? AppleAuthentication.formatFullName(credential.fullName) || null
        : null;
      const tokens = await unwrap(
        api.POST('/auth/apple', {
          body: { identity_token: credential.identityToken, nonce, full_name: fullName },
        }),
      );
      await session.start(tokens);
      return 'signedIn';
    },
  });
}
