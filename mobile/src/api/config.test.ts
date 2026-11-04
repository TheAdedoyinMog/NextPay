import { resolveApiBaseUrl } from './config';

// Importing the module resolves the real address, which needs a Metro host to exist.
jest.mock('expo-constants', () => ({ expoConfig: { hostUri: 'localhost:8081' } }));

describe('resolveApiBaseUrl', () => {
  it('uses Metro’s host with the API port in development', () => {
    expect(resolveApiBaseUrl(undefined, '192.168.1.78:8081')).toBe('http://192.168.1.78:8000');
  });

  it('prefers an explicit URL and drops any trailing slash', () => {
    expect(resolveApiBaseUrl('https://api.example.com/', '192.168.1.78:8081')).toBe(
      'https://api.example.com',
    );
  });

  it.each([[null], [undefined], ['']])('fails loudly with no address at all: %s', (hostUri) => {
    expect(() => resolveApiBaseUrl(undefined, hostUri)).toThrow('EXPO_PUBLIC_API_URL');
  });
});
