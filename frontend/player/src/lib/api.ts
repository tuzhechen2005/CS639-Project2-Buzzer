const BASE = '/api';

/**
 * Turn an error response body into a readable message. Backend errors are
 * `{error, message}`; FastAPI validation errors (422) put an array in `detail`.
 */
function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === 'object') {
    const { message, detail } = body as { message?: unknown; detail?: unknown };
    if (typeof message === 'string' && message) return message;
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (d && typeof d === 'object' ? (d as { msg?: unknown }).msg : undefined))
        .filter((m): m is string => typeof m === 'string' && m !== '');
      if (msgs.length) return msgs.join('; ');
    }
  }
  return `HTTP ${status}`;
}

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('token');
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.headers as Record<string, string> ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(errorMessage(body, res.status));
  }
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : ({} as T);
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined }),
};
