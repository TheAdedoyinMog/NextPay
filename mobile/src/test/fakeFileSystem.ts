/**
 * An in-memory stand-in for expo-file-system's `File` and `Paths`, mocked for every test in
 * jest.setup.js. It starts as an app that has launched before (the install marker exists), so
 * a test that puts a session in the Keychain keeps it. Import this module to look inside, or
 * call `uninstall()` to launch as a fresh install.
 */
export const files = new Set<string>();

const DOCUMENT = 'file:///document';

/** When set, writing a file throws, as with a full disk. */
export const failures = { write: false };

export const Paths = {
  get document() {
    return { uri: DOCUMENT };
  },
};

export class File {
  readonly uri: string;

  constructor(...parts: (string | { uri: string })[]) {
    this.uri = parts.map((part) => (typeof part === 'string' ? part : part.uri)).join('/');
  }

  get exists(): boolean {
    return files.has(this.uri);
  }

  create(): void {
    if (failures.write) {
      throw new Error('disk full');
    }
    files.add(this.uri);
  }
}

export const INSTALL_MARKER = `${DOCUMENT}/nextpay-installed`;

/** As iOS leaves things after deleting the app: the Documents directory is gone. */
export function uninstall(): void {
  files.clear();
}

/** The default: an app that has launched before. */
export function reset(): void {
  files.clear();
  files.add(INSTALL_MARKER);
  failures.write = false;
}

reset();
