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

  it('keeps the per-field problems of a 422', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        error: {
          code: 'validation_error',
          message: 'Check these fields: amount_cents',
          fields: { amount_cents: 'Input should be greater than 0' },
        },
      }),
    );

    await expect(getHealth()).rejects.toMatchObject({
      fields: { amount_cents: 'Input should be greater than 0' },
    });
  });

  it('has no fields for other errors', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(409, { error: { code: 'conflict', message: 'Not now.' } }),
    );

    await expect(getHealth()).rejects.toMatchObject({ fields: {} });
  });

  it.each([500, 502, 503])(
    'shows a friendly message for a %d without the envelope, never the status',
    async (status) => {
      fetchMock.mockResolvedValue(new Response('Internal Server Error', { status }));

      const error = await getHealth().catch((e: unknown) => e);

      expect(error).toMatchObject({
        status,
        code: 'http_error',
        message: 'Something went wrong on our side. Try again in a moment.',
      });
      expect(errorMessage(error)).not.toMatch(/status|\d{3}/);
    },
  );

  it('keeps the backend’s own message when a 5xx has the envelope', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(503, { error: { code: 'maintenance', message: 'Back in five minutes.' } }),
    );

    await expect(getHealth()).rejects.toMatchObject({ message: 'Back in five minutes.' });
  });

  it('gives a generic message for a 4xx without the envelope', async () => {
    fetchMock.mockResolvedValue(new Response('nope', { status: 418 }));

    await expect(getHealth()).rejects.toMatchObject({
      status: 418,
      message: 'Something went wrong. Try again.',
    });
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
