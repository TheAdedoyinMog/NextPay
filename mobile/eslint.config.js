const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');
const prettierConfig = require('eslint-config-prettier');

module.exports = defineConfig([
  expoConfig,
  prettierConfig,
  { ignores: ['src/api/schema.d.ts', 'dist/*', '.expo/*'] },
  {
    rules: {
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'All HTTP goes through src/api/client.ts (ADR 0012).' },
      ],
    },
  },
]);
