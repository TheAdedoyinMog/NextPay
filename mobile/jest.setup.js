/* global jest */
// react-native-safe-area-context's own Jest mock: fixed insets, since no native layout runs here.
jest.mock(
  'react-native-safe-area-context',
  () => jest.requireActual('react-native-safe-area-context/jest/mock').default,
);
