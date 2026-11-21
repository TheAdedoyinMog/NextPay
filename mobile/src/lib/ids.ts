/**
 * Ids the app makes for records it creates, so a retried request can't create a second one
 * (ADR 0015). They need to be unique, not secret: React Native has no Web Crypto, so where
 * `crypto.randomUUID` is missing, a version 4 UUID is built from `Math.random`.
 */
export function newId(): string {
  const randomUUID = (globalThis.crypto as { randomUUID?: () => string } | undefined)?.randomUUID;
  if (randomUUID) {
    return randomUUID.call(globalThis.crypto);
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const nibble = Math.floor(Math.random() * 16);
    return (char === 'x' ? nibble : (nibble % 4) + 8).toString(16);
  });
}
