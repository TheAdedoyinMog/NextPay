import Constants from 'expo-constants';

const LOCAL_API_PORT = 8000;

/**
 * An explicit URL wins. Otherwise, in development, the API is assumed to run on the
 * same computer as Metro, so the PC's address never has to be typed in (ADR 0012).
 */
export function resolveApiBaseUrl(explicitUrl?: string, metroHostUri?: string | null): string {
  if (explicitUrl) {
    return explicitUrl.replace(/\/+$/, '');
  }
  const host = metroHostUri?.split(':')[0];
  if (host) {
    return `http://${host}:${LOCAL_API_PORT}`;
  }
  throw new Error('No API address: set EXPO_PUBLIC_API_URL or start the app from Metro.');
}

export const API_BASE_URL = resolveApiBaseUrl(
  process.env.EXPO_PUBLIC_API_URL,
  Constants.expoConfig?.hostUri,
);
