/* global jest */
// react-native-safe-area-context's own Jest mock: fixed insets, since no native layout runs here.
jest.mock(
  'react-native-safe-area-context',
  () => jest.requireActual('react-native-safe-area-context/jest/mock').default,
);

// Native modules with no Jest build, replaced by fakes in src/test that tests can look inside.
// The file system starts with the install marker, as for an app that has launched before.
jest.mock('expo-file-system', () => jest.requireActual('@/test/fakeFileSystem'));
jest.mock('expo-apple-authentication', () => jest.requireActual('@/test/fakeAppleAuthentication'));
jest.mock('expo-crypto', () => jest.requireActual('@/test/fakeCrypto'));
