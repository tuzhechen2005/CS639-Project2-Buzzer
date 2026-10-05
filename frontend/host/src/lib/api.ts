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

async function throwForStatus(res: Response): Promise<never> {
  const body = await res.json().catch(() => null);
  throw new Error(errorMessage(body, res.status));
}

function authHeader(): Record<string, string> {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...authHeader(),
      ...(opts.headers as Record<string, string> ?? {}),
    },
  });
  if (!res.ok) await throwForStatus(res);
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : ({} as T);
}

/** Trigger a file download from an authenticated GET */
async function downloadFetch(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeader() });
  if (!res.ok) await throwForStatus(res);
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const match = disposition.match(/filename="([^"]+)"/);
  const filename = match ? match[1] : 'download';
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  // Firefox needs the link in the document, and the URL alive until the download starts.
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function jsonBody(body: unknown): BodyInit | undefined {
  return body !== undefined ? JSON.stringify(body) : undefined;
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'POST', body: jsonBody(body) }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'PUT', body: jsonBody(body) }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'PATCH', body: jsonBody(body) }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
  /** POST multipart/form-data (for file uploads); the browser sets the boundary */
  postForm: async <T>(path: string, form: FormData): Promise<T> => {
    const res = await fetch(`${BASE}${path}`, { method: 'POST', headers: authHeader(), body: form });
    if (!res.ok) await throwForStatus(res);
    const text = await res.text();
    return (text ? JSON.parse(text) : {}) as T;
  },
  download: downloadFetch,
};
