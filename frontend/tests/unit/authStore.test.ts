/** Unit tests for the auth store's token handling (Stage 1, T-1.3).
 *
 * The security contract under test (Stage 03, T-11): when the backend runs in
 * httpOnly-cookie mode (signalled by the readable `csrf_token` cookie), the
 * SPA must NOT keep a second, script-readable copy of the JWTs in
 * localStorage. Only the Bearer fallback (`USE_COOKIE_AUTH=false`) persists
 * tokens client-side. These tests pin both branches and the persisted shape
 * (profile only — never credential-shaped data).
 */
import { beforeEach, describe, expect, it } from "vitest";
import { tokenStore } from "@/lib/api";
import type { User } from "@/lib/types";
import { useAuthStore } from "@/stores/authStore";

const user: User = {
  id: "u1",
  email: "test@example.com",
  full_name: "Test User",
  role: "homeowner",
  is_active: true,
  subscription_active: false,
  subscription_plan: "free",
};

function setCookie(value: string) {
  document.cookie = value;
}

beforeEach(() => {
  localStorage.clear();
  document.cookie = "csrf_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  useAuthStore.setState({ user: null });
});

describe("setAuth — Bearer fallback mode (no csrf cookie)", () => {
  it("stores the tokens in the localStorage token store", () => {
    useAuthStore.getState().setAuth(user, "access-1", "refresh-1");
    expect(tokenStore.access).toBe("access-1");
    expect(tokenStore.refresh).toBe("refresh-1");
    expect(useAuthStore.getState().user).toEqual(user);
  });
});

describe("setAuth — httpOnly-cookie mode (csrf cookie present)", () => {
  it("refuses to duplicate tokens into localStorage", () => {
    setCookie("csrf_token=csrf-1; path=/");
    useAuthStore.getState().setAuth(user, "access-2", "refresh-2");
    expect(localStorage.getItem("sd_access")).toBeNull();
    expect(localStorage.getItem("sd_refresh")).toBeNull();
    expect(useAuthStore.getState().user).toEqual(user);
  });

  it("clears any pre-existing token copies when switching to cookie mode", () => {
    // Simulate a browser that had Bearer tokens from an older session…
    tokenStore.set("stale-access", "stale-refresh");
    setCookie("csrf_token=csrf-2; path=/");
    useAuthStore.getState().setAuth(user, "access-3", "refresh-3");
    expect(localStorage.getItem("sd_access")).toBeNull();
    expect(localStorage.getItem("sd_refresh")).toBeNull();
  });
});

describe("logout", () => {
  it("clears the user and every client-side token copy", () => {
    useAuthStore.getState().setAuth(user, "a", "r");
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().user).toBeNull();
    expect(localStorage.getItem("sd_access")).toBeNull();
    expect(localStorage.getItem("sd_refresh")).toBeNull();
  });
});

describe("persisted shape", () => {
  it("persists the profile only — never the tokens", () => {
    useAuthStore.getState().setAuth(user, "secret-access", "secret-refresh");
    const raw = localStorage.getItem("sd_auth");
    expect(raw).not.toBeNull();
    // zustand/persist envelope: { state: {...}, version: n }
    const { state } = JSON.parse(raw!) as { state: Record<string, unknown> };
    expect(state.user).toEqual(user);
    expect(state).not.toHaveProperty("access");
    expect(state).not.toHaveProperty("refresh");
    expect(raw).not.toContain("secret-access");
    expect(raw).not.toContain("secret-refresh");
  });
});
