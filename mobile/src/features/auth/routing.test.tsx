/**
 * The whole app, from launch: the real routes in src/app, the real session and client,
 * against a fake backend. These test the route guards, launch restore, and the auth flows.
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import * as SplashScreen from 'expo-splash-screen';

import { session } from '@/api/session';
import * as apple from '@/test/fakeAppleAuthentication';
import { createFakeBackend, type FakeBackend } from '@/test/fakeBackend';
import * as files from '@/test/fakeFileSystem';
import * as keychain from '@/test/fakeSecureStore';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));
jest.mock('expo-splash-screen', () => ({
  preventAutoHideAsync: jest.fn(async () => true),
  hideAsync: jest.fn(async () => undefined),
}));
// The app's real query client, minus the cache-cleanup timer that would outlive each test.
jest.mock('@/api/queryClient', () => {
  const actual = jest.requireActual('@/api/queryClient');
  return {
    ...actual,
    createQueryClient: () => {
      const client = actual.createQueryClient();
      client.setDefaultOptions({
        ...client.getDefaultOptions(),
        queries: { ...client.getDefaultOptions().queries, gcTime: Infinity },
        mutations: { ...client.getDefaultOptions().mutations, gcTime: Infinity },
      });
      return client;
    },
  };
});

let backend: FakeBackend;

function launch(initialUrl = '/') {
  return renderRouter('src/app', { initialUrl });
}

/** The account is past onboarding: it has an income source. */
function seedIncome(email = 'ada@example.com', name = 'Acme payroll') {
  backend.seed(email, '/income-sources', {
    name,
    expected_amount_cents: 150000,
    schedule: { type: 'biweekly', anchor_date: '2026-11-20' },
  });
}

/** The phone already holds a session from an earlier run, for an account that is set up. */
function rememberSession() {
  seedIncome();
  const tokens = backend.issueSession('ada@example.com');
  keychain.items.set(keychain.REFRESH_TOKEN_KEY, tokens.refresh_token);
  return tokens;
}

/** Opens the Setup tab, where the account and Log out live. */
async function openSetupTab() {
  await fireEvent.press(await screen.findByRole('button', { name: /^Setup, tab/ }));
}

async function fillIn(email: string, password: string) {
  await fireEvent.changeText(screen.getByLabelText('Email'), email);
  await fireEvent.changeText(screen.getByLabelText('Password'), password);
}

beforeEach(() => {
  keychain.reset();
  files.reset();
  apple.reset();
  jest.mocked(SplashScreen.hideAsync).mockClear();
  backend = createFakeBackend();
});

describe('launch', () => {
  it('shows sign-in when no session is stored', async () => {
    await launch();

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeTruthy();
    expect(screen).toHavePathname('/sign-in');
    expect(SplashScreen.hideAsync).toHaveBeenCalled();
  });

  it('restores a stored session and goes straight to the app', async () => {
    rememberSession();

    await launch();

    expect(await screen.findByText('Acme payroll')).toBeTruthy();
    expect(screen).toHavePathname('/');
  });

  it('keeps the splash up until the Keychain has been read', async () => {
    const pendingReads: ((token: string | null) => void)[] = [];
    const slowRead = () => new Promise<string | null>((resolve) => pendingReads.push(resolve));
    keychain.getItemAsync.mockImplementationOnce(slowRead).mockImplementationOnce(slowRead);
    // As on a cold start: nothing is known yet. (The session outlives each test's render.)
    void session.restore();

    await launch();
    expect(SplashScreen.hideAsync).not.toHaveBeenCalled();

    pendingReads.forEach((finishRead) => finishRead(null));
    await waitFor(() => expect(SplashScreen.hideAsync).toHaveBeenCalled());
  });

  it('stays signed in when offline, and says so', async () => {
    rememberSession();
    backend.offline = true;

    await launch();

    // Each section of Home reports it, after one retry.
    const alerts = await screen.findAllByRole('alert', undefined, { timeout: 10000 });
    expect(alerts[0]).toHaveTextContent('Could not reach the server at http://api.test.');
    expect(screen.getAllByText('You’re still signed in.').length).toBeGreaterThan(0);
    expect(screen).toHavePathname('/');
    expect(keychain.items.size).toBe(1);
  });

  it('sends a revoked session to sign-in, with the reason', async () => {
    rememberSession();
    backend.refreshFailsWith = 401;

    await launch();

    expect(await screen.findByText('Your session has ended. Sign in again.')).toBeTruthy();
    expect(screen).toHavePathname('/sign-in');
    expect(keychain.items.size).toBe(0);
  });
});

describe('a reinstall (ADR 0019)', () => {
  it('lands on sign-in, not the deleted install’s session', async () => {
    rememberSession(); // iOS kept this in the Keychain when the app was deleted
    files.uninstall();

    await launch();

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeTruthy();
    expect(screen).toHavePathname('/sign-in');
    expect(screen.queryByText('Your session has ended. Sign in again.')).toBeNull();
    expect(keychain.items.size).toBe(0);
    expect(backend.calls).toEqual([]);
  });
});

describe('Sign in with Apple', () => {
  const APPLE_ACCOUNT = `apple:${apple.appleId.user}`; // how the fake backend keys it

  async function pressApple() {
    await fireEvent.press(await screen.findByRole('button', { name: 'Sign in with Apple' }));
  }

  it('creates the account on first sign-in and goes to onboarding', async () => {
    await launch();

    await pressApple();

    expect(await screen.findByText('When do you get paid?')).toBeTruthy();
    expect(screen).toHavePathname('/onboarding');
    expect(backend.appleAccounts.get(apple.appleId.user)).toEqual({
      displayName: 'Ada Lovelace',
    });
  });

  it('signs in to the same account again after logging out, showing the name', async () => {
    seedIncome(APPLE_ACCOUNT);
    await launch();
    await pressApple();
    await openSetupTab();
    expect(await screen.findByText('Signed in as Ada Lovelace')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Log out' }));
    await screen.findByRole('button', { name: 'Sign in' });

    await pressApple(); // Apple no longer shares the name

    expect(await screen.findByText('Acme payroll')).toBeTruthy();
    await openSetupTab();
    expect(await screen.findByText('Signed in as Ada Lovelace')).toBeTruthy();
  });

  it('stays on sign-in, without an error, when the user closes Apple’s sheet', async () => {
    apple.next.outcome = 'cancel';
    await launch();

    await pressApple();

    await waitFor(() => expect(apple.signInAsync).toHaveBeenCalled());
    expect(screen).toHavePathname('/sign-in');
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('says what went wrong when Apple fails', async () => {
    apple.next.outcome = 'fail';
    await launch();

    await pressApple();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Sign in with Apple didn't work. Check that you're signed in to iCloud in Settings, then try again.",
    );
    expect(screen).toHavePathname('/sign-in');
  });

  it('is not offered where Sign in with Apple is unavailable', async () => {
    apple.isAvailableAsync.mockResolvedValueOnce(false);
    await launch();

    await screen.findByRole('button', { name: 'Sign in' });
    await waitFor(() => expect(apple.isAvailableAsync).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'Sign in with Apple' })).toBeNull();
  });
});

describe('route guards', () => {
  it('sends a signed-out user who opens the app to sign-in', async () => {
    await launch('/');

    await screen.findByRole('button', { name: 'Sign in' });
    expect(screen).toHavePathname('/sign-in');
    expect(screen.queryByText(/Signed in as/)).toBeNull();
  });

  it('keeps a signed-in user out of the auth screens', async () => {
    rememberSession();

    await launch('/sign-up');

    expect(await screen.findByText('Acme payroll')).toBeTruthy();
    expect(screen).toHavePathname('/');
  });
});

describe('flows', () => {
  it('signs in and lands on Home when the account is set up', async () => {
    backend.addUser('ada@example.com', 'correct horse battery');
    seedIncome();
    await launch();
    await screen.findByRole('button', { name: 'Sign in' });

    await fillIn('ada@example.com', 'correct horse battery');
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Acme payroll')).toBeTruthy();
    expect(screen).toHavePathname('/');
  });

  it('signs in to onboarding when the account has no income yet', async () => {
    backend.addUser('ada@example.com', 'correct horse battery');
    await launch();
    await screen.findByRole('button', { name: 'Sign in' });

    await fillIn('ada@example.com', 'correct horse battery');
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('When do you get paid?')).toBeTruthy();
    expect(screen).toHavePathname('/onboarding');
  });

  it('shows wrong credentials on the sign-in screen', async () => {
    await launch();
    await screen.findByRole('button', { name: 'Sign in' });

    await fillIn('ada@example.com', 'nope');
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Incorrect email or password.')).toBeTruthy();
    expect(screen).toHavePathname('/sign-in');
  });

  it('shows a sign-up 422 naming the field, then creates the account', async () => {
    await launch('/sign-up');
    await screen.findByRole('button', { name: 'Create account' });

    await fillIn('new@example.com', 'short');
    await fireEvent.press(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('Check these fields: password')).toBeTruthy();

    await fillIn('new@example.com', 'a long passphrase');
    await fireEvent.press(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('When do you get paid?')).toBeTruthy();
  });

  it('logs out back to sign-in, ending the session on the backend', async () => {
    const tokens = rememberSession();
    await launch();
    await openSetupTab();
    await screen.findByText('Signed in as ada@example.com');

    await fireEvent.press(screen.getByRole('button', { name: 'Log out' }));

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeTruthy();
    expect(screen).toHavePathname('/sign-in');
    expect(screen.queryByText('Your session has ended. Sign in again.')).toBeNull();
    expect(keychain.items.size).toBe(0);
    await waitFor(() => expect(backend.isRevoked(tokens.refresh_token)).toBe(true));
  });

  it('shows the next account none of the previous account’s data', async () => {
    backend.addUser('grace@example.com', 'another long passphrase');
    seedIncome('grace@example.com', 'Grace’s studio');
    rememberSession();
    await launch();
    await openSetupTab();
    await screen.findByText('Signed in as ada@example.com');
    await fireEvent.press(screen.getByRole('button', { name: 'Log out' }));
    await screen.findByRole('button', { name: 'Sign in' });

    await fillIn('grace@example.com', 'another long passphrase');
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Grace’s studio')).toBeTruthy();
    expect(screen.queryByText('Acme payroll')).toBeNull();
    expect(screen.queryByText('Signed in as ada@example.com')).toBeNull();
  });
});
