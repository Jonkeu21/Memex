import type { ApiError } from '../types/api';

const TOKEN_KEY = 'memex.dashboard.bearerToken';

export const tokenStorage = {
  get(): string {
    try {
      return localStorage.getItem(TOKEN_KEY) ?? '';
    } catch {
      return '';
    }
  },
  set(value: string): void {
    try {
      if (value) {
        localStorage.setItem(TOKEN_KEY, value);
      } else {
        localStorage.removeItem(TOKEN_KEY);
      }
    } catch {
      /* localStorage may be disabled — fail silently */
    }
  },
};

export interface FetchOptions extends RequestInit {
  json?: unknown;
  /** When true, attach the bearer token from localStorage. */
  withAuth?: boolean;
  /** Search params to append. */
  params?: Record<string, string | number | boolean | null | undefined>;
}

const buildUrl = (path: string, params?: FetchOptions['params']): string => {
  if (!params) return path;
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue;
    usp.set(k, String(v));
  }
  const qs = usp.toString();
  return qs ? `${path}?${qs}` : path;
};

export class ApiHttpError extends Error implements ApiError {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiHttpError';
    this.status = status;
    this.code = code;
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  options: FetchOptions = {},
): Promise<T> {
  const { json, withAuth, params, headers, ...rest } = options;
  const finalHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...(headers as Record<string, string> | undefined),
  };
  if (json !== undefined) {
    finalHeaders['Content-Type'] = 'application/json';
  }
  if (withAuth) {
    const token = tokenStorage.get();
    if (token) {
      finalHeaders.Authorization = `Bearer ${token}`;
    }
  }

  const response = await fetch(buildUrl(path, params), {
    ...rest,
    headers: finalHeaders,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });

  if (!response.ok) {
    let code = 'http_error';
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (payload?.detail?.error?.code) {
        code = payload.detail.error.code;
        message = payload.detail.error.message ?? message;
      } else if (payload?.error?.code) {
        code = payload.error.code;
        message = payload.error.message ?? message;
      } else if (payload?.detail) {
        message = typeof payload.detail === 'string'
          ? payload.detail
          : JSON.stringify(payload.detail);
      }
    } catch {
      /* response wasn't JSON; keep the status-line message */
    }
    throw new ApiHttpError(response.status, code, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
