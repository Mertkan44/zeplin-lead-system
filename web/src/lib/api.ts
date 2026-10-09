// The one HTTP client for the dashboard. Every API call goes through
// apiRequest: same-origin cookies, JSON in and out, and a 401 from any CRM
// endpoint ends the session (App clears CRM state and shows the login).
// A 403 only means "not allowed" and keeps the session.

export const SESSION_EXPIRED_EVENT = 'zeplin:session-expired';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly data: Record<string, unknown>;

  constructor(status: number, data: Record<string, unknown>) {
    super(typeof data.error === 'string' && data.error ? data.error : `request_failed_${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = typeof data.code === 'string' ? data.code : undefined;
    this.data = data;
  }
}

export interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  keepalive?: boolean;
  signal?: AbortSignal;
}

export function notifyIfSessionExpired(response: Response, url: string = response.url): void {
  if (response.status === 401 && !String(url || '').includes('/api/auth')) {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  }
}

export async function apiRequest<T = Record<string, unknown>>(url: string, options: ApiRequestOptions = {}): Promise<T> {
  const init: RequestInit = {
    method: options.method || 'GET',
    credentials: 'same-origin',
    keepalive: options.keepalive,
    signal: options.signal,
  };
  if (options.body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(url, init);
  notifyIfSessionExpired(response, url);
  const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) throw new ApiError(response.status, data);
  return data as T;
}
