import { api, ApiError, errorMessage, setAuthHandler, unwrap } from './client';

jest.mock('./config', () => ({ API_BASE_URL: 'http://api.test' }));

const fetchMock = jest.fn<Promise<Response>, [Request, RequestInit?]>();

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function getHealth() {
  return unwrap(api.GET('/health'));
}

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
  setAuthHandler({ getAccessToken: async () => null, refreshAccessToken: async () => null });
});

describe('requests', () => {
  it('goes to the configured base URL and returns the data', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { status: 'ok', engine_version: '1.2.3' }));

    await expect(getHealth()).resolves.toEqual({ status: 'ok', engine_version: '1.2.3' });
    expect(fetchMock.mock.calls[0]?.[0].url).toBe('http://api.test/health');
  });

  it('sends the session’s token as a bearer header', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, {}));
    setAuthHandler({ getAccessToken: async () => 'a-token', refreshAccessToken: async () => null });

    await getHealth();

    expect(fetchMock.mock.calls[0]?.[0].headers.get('Authorization')).toBe('Bearer a-token');
  });

  it('sends no header when signed out', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, {}));

    await getHealth();

    expect(fetchMock.mock.calls[0]?.[0].headers.get('Authorization')).toBeNull();
  });

  it('gives up on a server that never answers, and says it timed out', async () => {
    jest.useFakeTimers();
    try {
      fetchMock.mockImplementation(
        (_request, init) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
          }),
      );

      const call = getHealth();
      const failure = expect(call).rejects.toMatchObject({
        status: 0,
        code: 'timeout',
        message: 'The server at http://api.test took too long to answer.',
      });
      await jest.advanceTimersByTimeAsync(15_000);
      await failure;
    } finally {
      jest.useRealTimers();
    }
  });
});

describe('errors', () => {
  it('keeps the backend’s code and message, which name the fields on a 422', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        error: { code: 'validation_error', message: 'Check these fields: deadline' },
      }),
    );

    const error = await getHealth().catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: 'validation_error',
      message: 'Check these fields: deadline',
    });
  });

  it('copes with an error body that is not the envelope', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 }));

    await expect(getHealth()).rejects.toMatchObject({ status: 502, code: 'http_error' });
  });

  it('names the address when no response arrives', async () => {
    fetchMock.mockRejectedValue(new TypeError('Network request failed'));

    await expect(getHealth()).rejects.toMatchObject({
      status: 0,
      code: 'network_error',
      message: 'Could not reach the server at http://api.test.',
    });
  });
});

describe('errorMessage', () => {
  it('shows the backend’s message, and a generic one for anything unexpected', () => {
    expect(errorMessage(new ApiError(409, 'email_unavailable', 'Not this email.'))).toBe(
      'Not this email.',
    );
    expect(errorMessage(new Error('a bug'))).toBe('Something went wrong. Try again.');
  });
});
