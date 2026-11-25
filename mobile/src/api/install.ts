/**
 * Whether this is the app's first launch since it was installed (ADR 0019).
 *
 * iOS keeps Keychain items after an app is deleted, but deletes the app's Documents directory.
 * So a marker file there, written at the first launch, is missing exactly when the app has
 * been installed (or reinstalled) since. Restoring a device backup brings the marker back but
 * not the session: the refresh token is stored "this device only" (ADR 0013).
 */
import { File, Paths } from 'expo-file-system';

const MARKER_NAME = 'nextpay-installed';

function marker(): File {
  return new File(Paths.document, MARKER_NAME);
}

export function isFreshInstall(): boolean {
  return !marker().exists;
}

/** Records that this install has launched. Throws if the file can't be written. */
export function markInstalled(): void {
  marker().create({ overwrite: true });
}
