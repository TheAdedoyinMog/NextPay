/** expo-crypto on Node's crypto, mocked for every test in jest.setup.js. */

// Required rather than imported: the app's tsconfig has no Node types, and needs none.
const { createHash, randomBytes } = jest.requireActual<{
  createHash(algorithm: 'sha256'): { update(data: string): { digest(encoding: 'hex'): string } };
  randomBytes(size: number): Uint8Array;
}>('crypto');

export const CryptoDigestAlgorithm = { SHA256: 'SHA-256' } as const;

/** SHA-256 as lowercase hex, which is what expo-crypto returns by default. */
export function sha256Hex(data: string): string {
  return createHash('sha256').update(data).digest('hex');
}

export async function digestStringAsync(_algorithm: string, data: string): Promise<string> {
  return sha256Hex(data);
}

export function getRandomBytes(count: number): Uint8Array {
  return new Uint8Array(randomBytes(count));
}
