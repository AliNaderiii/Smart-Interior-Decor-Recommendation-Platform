/** Axios client with automatic JWT refresh.
 *
 * V2 (OWASP A02): the backend now issues httpOnly `access_token` /
 * `refresh_token` cookies, so the browser holds credentials that JavaScript
 * — and therefore any XSS — cannot read. `withCredentials` makes axios send
 * them. Because cookies ride along automatically, state-changing requests
 * must echo the readable `csrf_token` cookie in `X-CSRF-Token`
 * (double-submit); an attacker on another origin can cause the cookie to be
 * sent but cannot read it to build the header.
 *
 * The localStorage token path is retained as a fallback so non-cookie
 * clients (and the dev `USE_COOKIE_AUTH=false` mode) keep working.
 */
import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

export const api = axios.create({ baseURL: "/api/v1", withCredentials: true });

const CSRF_COOKIE = "csrf_token";
const UNSAFE = new Set(["post", "put", "patch", "delete"]);

/** Read a non-httpOnly cookie by name. */
function readCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}=([^;]*)`),
  );
  return match ? decodeURIComponent(match[1]) : null;
}

const ACCESS_KEY = "sd_access";
const REFRESH_KEY = "sd_refresh";

export const tokenStore = {
  get access() { return localStorage.getItem(ACCESS_KEY); },
  get refresh() { return localStorage.getItem(REFRESH_KEY); },
  set(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

api.interceptors.request.use((config) => {
  const token = tokenStore.access;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // Double-submit CSRF: echo the readable cookie on state-changing verbs.
  if (UNSAFE.has((config.method ?? "get").toLowerCase())) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) config.headers["X-CSRF-Token"] = csrf;
  }
  return config;
});

let refreshing: Promise<void> | null = null;

async function doRefresh(): Promise<void> {
  const refresh = tokenStore.refresh;
  const csrf = readCookie(CSRF_COOKIE);
  // With cookie auth the refresh token travels in the httpOnly cookie, so an
  // empty body is valid — the server reads the cookie.
  const { data } = await axios.post(
    "/api/v1/auth/refresh",
    refresh ? { refresh_token: refresh } : {},
    { withCredentials: true, headers: csrf ? { "X-CSRF-Token": csrf } : undefined },
  );
  if (data?.data?.access_token) {
    tokenStore.set(data.data.access_token, data.data.refresh_token);
  }
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retried?: boolean };
    const canRefresh = Boolean(tokenStore.refresh) || Boolean(readCookie(CSRF_COOKIE));
    if (error.response?.status === 401 && !original._retried && canRefresh) {
      original._retried = true;
      try {
        refreshing = refreshing ?? doRefresh();
        await refreshing;
        refreshing = null;
        return api(original);
      } catch {
        refreshing = null;
        tokenStore.clear();
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

/** Standard envelope from the backend: {success, data, error} */
export interface Envelope<T> {
  success: boolean;
  data: T;
  error: string | null;
}

export async function get<T>(url: string): Promise<T> {
  const { data } = await api.get<Envelope<T>>(url);
  return data.data;
}

export async function post<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await api.post<Envelope<T>>(url, body);
  return data.data;
}

export async function patch<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await api.patch<Envelope<T>>(url, body);
  return data.data;
}

export async function del<T>(url: string): Promise<T> {
  const { data } = await api.delete<Envelope<T>>(url);
  return data.data;
}
