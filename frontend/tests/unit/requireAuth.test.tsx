/** Unit tests for the route guard (Stage 1, T-1.4).
 *
 * Pins the session-establishment contract after the cookie-mode fix:
 * a session is established when the profile is known AND the credentials
 * live somewhere — a Bearer token in the token store, or the backend's
 * httpOnly-cookie pair (signalled by the readable `csrf_token` cookie).
 *
 * Regression under test: before T-1.4, `RequireAuth` demanded
 * `tokenStore.access` unconditionally, so in the DEFAULT cookie mode
 * (USE_COOKIE_AUTH=true, where setAuth deliberately clears localStorage
 * tokens) every authenticated route bounced a valid session back to
 * /login — the logged-in half of the product was unreachable.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { RequireAuth } from "@/components/guards";
import { tokenStore } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";

const HOMEOWNER = {
  id: "u1",
  email: "demo@smartdecor.dev",
  full_name: "Demo Owner",
  role: "homeowner" as const,
  is_active: true,
  subscription_active: false,
  subscription_plan: "free",
};
const ADMIN = { ...HOMEOWNER, id: "u2", email: "admin@smartdecor.dev", role: "admin" as const };

function renderGuard(path = "/quiz", roles?: string[]) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/quiz"
          element={<RequireAuth roles={roles}><div>QUIZ CONTENT</div></RequireAuth>}
        />
        <Route path="/admin/products" element={<div>ADMIN CONTENT</div>} />
        <Route path="/login" element={<div>LOGIN WALL</div>} />
        <Route path="/" element={<div>HOME CONTENT</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  document.cookie = "csrf_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  useAuthStore.setState({ user: null });
});

describe("cookie-mode session (the default: USE_COOKIE_AUTH=true)", () => {
  it("passes a valid cookie-mode session through (user + csrf cookie, NO local tokens)", () => {
    document.cookie = "csrf_token=valid-session; path=/";
    useAuthStore.setState({ user: HOMEOWNER });
    renderGuard("/quiz");
    expect(screen.queryByText("QUIZ CONTENT")).not.toBeNull();
    expect(screen.queryByText("LOGIN WALL")).toBeNull();
  });

  it("still blocks anonymous visitors even when the csrf cookie is stale", () => {
    // No profile at all: the cookie alone must not unlock the app.
    document.cookie = "csrf_token=stale; path=/";
    useAuthStore.setState({ user: null });
    renderGuard("/quiz");
    expect(screen.queryByText("LOGIN WALL")).not.toBeNull();
  });
});

describe("Bearer mode (USE_COOKIE_AUTH=false)", () => {
  it("passes a token session through", () => {
    tokenStore.set("access-x", "refresh-x");
    useAuthStore.setState({ user: HOMEOWNER });
    renderGuard("/quiz");
    expect(screen.queryByText("QUIZ CONTENT")).not.toBeNull();
  });

  it("blocks a profile without tokens and without cookies (logged-out after tab close)", () => {
    useAuthStore.setState({ user: HOMEOWNER });
    renderGuard("/quiz");
    expect(screen.queryByText("LOGIN WALL")).not.toBeNull();
  });
});

describe("role enforcement", () => {
  it("redirects a homeowner away from admin-only routes to / (not /login)", () => {
    document.cookie = "csrf_token=session; path=/";
    useAuthStore.setState({ user: HOMEOWNER });
    render(
      <MemoryRouter initialEntries={["/admin/products"]}>
        <Routes>
          <Route
            path="/admin/products"
            element={
              <RequireAuth roles={["admin"]}>
                <div>ADMIN CONTENT</div>
              </RequireAuth>
            }
          />
          <Route path="/" element={<div>HOME CONTENT</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.queryByText("HOME CONTENT")).not.toBeNull();
    expect(screen.queryByText("ADMIN CONTENT")).toBeNull();
  });

  it("lets an admin into an admin-only route", () => {
    document.cookie = "csrf_token=session; path=/";
    useAuthStore.setState({ user: ADMIN });
    render(
      <MemoryRouter initialEntries={["/admin/products"]}>
        <Routes>
          <Route
            path="/admin/products"
            element={
              <RequireAuth roles={["admin"]}>
                <div>ADMIN CONTENT</div>
              </RequireAuth>
            }
          />
          <Route path="/" element={<div>HOME CONTENT</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.queryByText("ADMIN CONTENT")).not.toBeNull();
  });
});
