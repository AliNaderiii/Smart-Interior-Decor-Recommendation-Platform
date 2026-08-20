/** HTTP client with automatic JWT refresh — zero dependencies.
 *
 * V2 (Phase 2, performance): this module used to wrap axios. axios was the
 * only reason `axios` sat in the eager `query` chunk (~13 KB gzip on every
 * route) and it was used for nothing beyond two interceptors and JSON
 * bodies — both of which `fetch` does natively. Rewritten on `fetch`, the
 * public surface (`api.get/post/patch/delete`, `get/post/patch/del`,
 * `tokenStore`, `Envelope`) is unchanged, so no call site had to move.
 *
 * V2 (Phase 1, OWASP A02): the backend issues httpOnly `access_token` /
 * `refresh_token` cookies, so credentials are unreadable to JavaScript — and
 * therefore to XSS. `credentials: "include"` sends them. Because cookies ride
 * along automatically, state-changing requests echo the readable `csrf_token`
 * cookie in `X-CSRF-Token` (double-submit): a cross-origin attacker can cause
 * the cookie to be sent but cannot read it to construct the header.
 *
 * The localStorage token path is retained for Bearer clients and for the dev
 * `USE_COOKIE_AUTH=false` mode.
 */

const BASE_URL = "/api/v1";
const ACCESS_KEY = "sd_access";
const REFRESH_KEY = "sd_refresh";
const CSRF_COOKIE = "csrf_token";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export const tokenStore = {
  get access() {
    return localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

/** Read a non-httpOnly cookie by name. */
function readCookie(name: string): string | null {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/** Standard envelope from the backend: {success, data, error} */
export interface Envelope<T> {
  success: boolean;
  data: T;
  error: string | null;
}

/** Error carrying the HTTP status, so callers can branch on 401/403/429. */
export class ApiError extends Error {
  // Plain fields + assignment: TS `erasableSyntaxOnly` forbids parameter
  // properties, since they emit runtime code.
  status: number;
  body?: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** Internal: prevents infinite refresh recursion. */
  _retried?: boolean;
}

function buildHeaders(method: string, hasJsonBody: boolean): Headers {
  const headers = new Headers();
  // FormData must NOT get an explicit Content-Type — the browser has to set
  // the multipart boundary itself.
  if (hasJsonBody) headers.set("Content-Type", "application/json");
  const token = tokenStore.access;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (UNSAFE.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  return headers;
}

let refreshing: Promise<void> | null = null;

async function doRefresh(): Promise<void> {
  const refresh = tokenStore.refresh;
  const csrf = readCookie(CSRF_COOKIE);
  const headers = new Headers({ "Content-Type": "application/json" });
  if (csrf) headers.set("X-CSRF-Token", csrf);

  // With cookie auth the refresh token travels in the httpOnly cookie, so an
  // empty body is valid — the server reads the cookie.
  const resp = await fetch(`${BASE_URL}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify(refresh ? { refresh_token: refresh } : {}),
  });
  if (!resp.ok) throw new ApiError(resp.status, "refresh failed");
  const json = (await resp.json()) as Envelope<{
    access_token?: string;
    refresh_token?: string;
  }>;
  if (json?.data?.access_token && json.data.refresh_token) {
    tokenStore.set(json.data.access_token, json.data.refresh_token);
  }
}

async function request<T>(url: string, options: RequestOptions = {}): Promise<Envelope<T>> {
  const method = (options.method ?? "GET").toUpperCase();
  const isForm = options.body instanceof FormData;
  const hasBody = options.body !== undefined;

  const resp = await fetch(`${BASE_URL}${url}`, {
    method,
    credentials: "include",
    headers: buildHeaders(method, hasBody && !isForm),
    body: isForm
      ? (options.body as FormData)
      : hasBody
        ? JSON.stringify(options.body)
        : undefined,
    signal: options.signal,
  });

  // Transparently refresh an expired access token once, then replay.
  const canRefresh = Boolean(tokenStore.refresh) || Boolean(readCookie(CSRF_COOKIE));
  if (resp.status === 401 && !options._retried && canRefresh) {
    try {
      refreshing = refreshing ?? doRefresh();
      await refreshing;
      refreshing = null;
      return request<T>(url, { ...options, _retried: true });
    } catch {
      refreshing = null;
      tokenStore.clear();
      window.location.href = "/login";
      throw new ApiError(401, "session expired");
    }
  }

  let payload: Envelope<T> | undefined;
  try {
    payload = (await resp.json()) as Envelope<T>;
  } catch {
    payload = undefined;
  }

  if (!resp.ok) {
    throw new ApiError(
      resp.status,
      payload?.error ?? `Request failed with status ${resp.status}`,
      payload,
    );
  }
  return payload as Envelope<T>;
}

/** axios-compatible surface, kept so existing call sites need no changes. */
export const api = {
  get: <T>(url: string, opts?: RequestOptions) =>
    request<T>(url, { ...opts, method: "GET" }).then((data) => ({ data })),
  post: <T>(url: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(url, { ...opts, method: "POST", body }).then((data) => ({ data })),
  patch: <T>(url: string, body?: unknown, opts?: RequestOptions) =>
    request<T>(url, { ...opts, method: "PATCH", body }).then((data) => ({ data })),
  delete: <T>(url: string, opts?: RequestOptions) =>
    request<T>(url, { ...opts, method: "DELETE" }).then((data) => ({ data })),
};

export async function get<T>(url: string, signal?: AbortSignal): Promise<T> {
  return (await request<T>(url, { method: "GET", signal })).data;
}

export async function post<T>(url: string, body?: unknown): Promise<T> {
  return (await request<T>(url, { method: "POST", body })).data;
}

export async function patch<T>(url: string, body?: unknown): Promise<T> {
  return (await request<T>(url, { method: "PATCH", body })).data;
}

export async function del<T>(url: string): Promise<T> {
  return (await request<T>(url, { method: "DELETE" })).data;
}
