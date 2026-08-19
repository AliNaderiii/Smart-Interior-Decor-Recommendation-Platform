/** Axios client with automatic JWT refresh.
 *
 * MVP stores tokens in localStorage (documented httpOnly-cookie path in
 * docs/ARCHITECTURE.md §Auth). The interceptor transparently refreshes an
 * expired access token once, then replays the failed request.
 */
import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

export const api = axios.create({ baseURL: "/api/v1" });

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
  return config;
});

let refreshing: Promise<void> | null = null;

async function doRefresh(): Promise<void> {
  const refresh = tokenStore.refresh;
  if (!refresh) throw new Error("no refresh token");
  const { data } = await axios.post("/api/v1/auth/refresh", { refresh_token: refresh });
  tokenStore.set(data.data.access_token, data.data.refresh_token);
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retried?: boolean };
    if (error.response?.status === 401 && !original._retried && tokenStore.refresh) {
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
