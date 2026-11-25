/**
 * The signed-in session: where tokens live and how they are refreshed (ADR 0013).
 *
 * - The refresh token is kept in the iOS Keychain (expo-secure-store), on this device only. A
 *   fresh install clears it first, since the Keychain outlives a deleted app (ADR 0019).
 * - The access token is kept in memory only. After a launch the first request refreshes.
 * - "Signed in" means holding a refresh token the server hasn't rejected. Only a rejected
 *   refresh (a 401 from /auth/refresh) signs the user out. A network error or timeout never does.
 * - Refresh is single-flight. The backend rotates refresh tokens and treats a reused one as
 *   theft (ADR 0009), so two concurrent refreshes would end the session. Every caller awaits
 *   the same refresh.
 */
import * as SecureStore from 'expo-secure-store';

import { api, ApiError, type AuthHandler, setAuthHandler, unwrap } from './client';
import { isFreshInstall, markInstalled } from './install';
import type { components } from './schema';

type TokenResponse = components['schemas']['TokenResponse'];

/** Why nobody is signed in: never was, chose to log out, or the server ended the session. */
export type SignOutReason = 'none' | 'loggedOut' | 'ended';

export type SessionState =
  { status: 'restoring' } | { status: 'signedIn' } | { status: 'signedOut'; reason: SignOutReason };

const REFRESH_TOKEN_KEY = 'nextpay.refresh_token';
// THIS_DEVICE_ONLY: never in a backup, so restoring a backup to another phone carries no session.
const KEYCHAIN_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

const RESTORING: SessionState = { status: 'restoring' };
const SIGNED_IN: SessionState = { status: 'signedIn' };

class Session implements AuthHandler {
  private state: SessionState = RESTORING;
  private readonly listeners = new Set<() => void>();
  private refreshToken: string | null = null;
  private accessToken: string | null = null;
  private refreshing: Promise<string | null> | null = null;
  /**
   * Goes up on every sign-in and sign-out. Work that finishes in a different epoch from the
   * one it started in is discarded, so a refresh that completes after logout can't put a
   * token back.
   */
  private epoch = 0;

  readonly getState = (): SessionState => this.state;

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /**
   * Reads the Keychain at launch. No network: an offline launch stays signed in. A fresh
   * install starts signed out, whatever an earlier install left in the Keychain.
   */
  async restore(): Promise<void> {
    const epoch = this.reset();
    this.setState(RESTORING);
    let stored: string | null = null;
    try {
      stored = isFreshInstall()
        ? await this.forgetEarlierInstall()
        : await SecureStore.getItemAsync(REFRESH_TOKEN_KEY, KEYCHAIN_OPTIONS);
    } catch {
      stored = null; // an unreadable Keychain can't hold a session we could use
    }
    if (epoch !== this.epoch) {
      return; // signed in while the Keychain was being read
    }
    this.refreshToken = stored;
    this.setState(stored ? SIGNED_IN : { status: 'signedOut', reason: 'none' });
  }

  /**
   * iOS keeps Keychain items after the app is deleted, so a reinstalled app would wake up with
   * the deleted app's session (ADR 0019). Clear first, then mark the install: if the app stops
   * in between, the next launch just clears again. If clearing fails, nothing is marked and
   * this launch is signed out anyway.
   */
  private async forgetEarlierInstall(): Promise<null> {
    await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY, KEYCHAIN_OPTIONS);
    markInstalled();
    return null;
  }

  /** Begins a session with the tokens from sign-up, log-in, or Sign in with Apple. */
  async start(tokens: TokenResponse): Promise<void> {
    const epoch = this.reset();
    this.refreshToken = tokens.refresh_token;
    this.accessToken = tokens.access_token;
    try {
      await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, tokens.refresh_token, KEYCHAIN_OPTIONS);
    } catch (error) {
      this.reset();
      throw error;
    }
    if (epoch === this.epoch) {
      this.setState(SIGNED_IN);
    }
  }

  /** Logs out this device: clears it locally at once, then revokes on the backend if it can. */
  async signOut(): Promise<void> {
    const refreshToken = this.refreshToken;
    await this.end('loggedOut');
    if (refreshToken) {
      // Best effort. Offline, the token is gone from the phone, so nobody can use it here.
      api.POST('/auth/logout', { body: { refresh_token: refreshToken } }).catch(() => undefined);
    }
  }

  async getAccessToken(): Promise<string | null> {
    if (this.accessToken) {
      return this.accessToken;
    }
    return this.refreshToken ? this.refreshOnce() : null;
  }

  async refreshAccessToken(rejected: string): Promise<string | null> {
    if (this.accessToken && this.accessToken !== rejected) {
      return this.accessToken; // someone else already refreshed while this request was out
    }
    this.accessToken = null;
    return this.refreshToken ? this.refreshOnce() : null;
  }

  private refreshOnce(): Promise<string | null> {
    if (!this.refreshing) {
      const refreshing = this.refresh().finally(() => {
        if (this.refreshing === refreshing) {
          this.refreshing = null;
        }
      });
      this.refreshing = refreshing;
    }
    return this.refreshing;
  }

  private async refresh(): Promise<string | null> {
    const epoch = this.epoch;
    const refreshToken = this.refreshToken;
    if (!refreshToken) {
      return null;
    }
    let tokens: TokenResponse;
    try {
      tokens = await unwrap(api.POST('/auth/refresh', { body: { refresh_token: refreshToken } }));
    } catch (error) {
      if (epoch !== this.epoch) {
        return null;
      }
      if (error instanceof ApiError && error.status === 401) {
        await this.end('ended'); // rejected, expired, or revoked: the only way out besides logout
        return null;
      }
      throw error; // network error, timeout, 5xx: still signed in, the next request tries again
    }
    if (epoch !== this.epoch) {
      return null;
    }
    this.refreshToken = tokens.refresh_token;
    this.accessToken = tokens.access_token;
    try {
      await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, tokens.refresh_token, KEYCHAIN_OPTIONS);
    } catch {
      // The session still works until the app closes; the next launch will have to sign in.
    }
    return tokens.access_token;
  }

  private async end(reason: SignOutReason): Promise<void> {
    this.reset();
    this.setState({ status: 'signedOut', reason });
    try {
      await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY, KEYCHAIN_OPTIONS);
    } catch {
      // The token stays in the Keychain, but the backend rejects it at the next refresh.
    }
  }

  private reset(): number {
    this.epoch += 1;
    this.refreshToken = null;
    this.accessToken = null;
    this.refreshing = null;
    return this.epoch;
  }

  private setState(state: SessionState): void {
    this.state = state;
    this.listeners.forEach((listener) => listener());
  }
}

export const session = new Session();
setAuthHandler(session);
