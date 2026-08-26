/** Unit tests for the login form's failure path (Stage 1, T-1.4).
 *
 * The DOM-side twin of the Playwright auth-negative spec: a failed login
 * must (1) show the server's message as plain, escaped text — never as
 * live HTML — (2) keep the user on /login, and (3) never navigate to an
 * admin route.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>();
  return { ...orig, post: postMock };
});

import { ApiError } from "@/lib/api";
import LoginPage from "@/pages/LoginPage";

function renderLogin(path = "/login") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/admin/products" element={<div>ADMIN PAGE</div>} />
        <Route path="/quiz" element={<div>QUIZ PAGE</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  document.cookie = "csrf_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  postMock.mockReset();
});

async function submitLogin(email: string, password: string) {
  await userEvent.type(screen.getByLabelText(/email/i), email);
  await userEvent.type(screen.getByLabelText(/password/i), password);
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
}

describe("login failure path", () => {
  it("shows the server's message (ApiError.message), not the stale axios-shaped fallback", async () => {
    postMock.mockRejectedValue(
      new ApiError(401, "Invalid credentials", { success: false, data: null, error: "Invalid credentials" }),
    );
    const { container } = renderLogin();
    await submitLogin("x@y.com", "WrongPass1!");

    await waitFor(() => expect(screen.getByText("Invalid credentials")).toBeTruthy());
    // The old code read err.response?.data?.error (always undefined on this
    // fetch-based client) and fell back to "Login failed".
    expect(screen.queryByText("Login failed")).toBeNull();
    // The error is plain text: no HTML structure from the message.
    const errorNode = screen.getByText("Invalid credentials");
    expect(errorNode.tagName).toBe("P");
    expect(container.innerHTML).not.toContain("<script");
  });

  it("keeps the user on /login after a failed attempt (no admin redirect)", async () => {
    postMock.mockRejectedValue(new ApiError(401, "Invalid credentials"));
    renderLogin("/login");
    await submitLogin("demo@smartdecor.dev", "WrongPass1!");

    await waitFor(() => expect(screen.getByText("Invalid credentials")).toBeTruthy());
    expect(screen.queryByText("ADMIN PAGE")).toBeNull();
    expect(screen.queryByText("QUIZ PAGE")).toBeNull();
    // The login form is still there, ready for a corrected attempt.
    expect(screen.getByRole("button", { name: /sign in/i })).toBeTruthy();
  });

  it("renders an HTML-looking server message as escaped text, never live HTML", async () => {
    // Defense in depth: even if a future backend ever reflected input in the
    // error string, React renders it as text.
    const evil = '"><img src=x onerror="window.__xss_fired=true">';
    postMock.mockRejectedValue(new ApiError(401, evil));
    const { container } = renderLogin();
    await submitLogin("x@y.com", "WrongPass1!");

    await waitFor(() =>
      expect(screen.queryByText("Invalid credentials") ?? screen.queryByText(evil)).toBeTruthy(),
    );
    expect(container.querySelector('img[src="x"]')).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("falls back to the safe generic message for non-ApiError failures", async () => {
    postMock.mockRejectedValue(new TypeError("NetworkError: failed to fetch"));
    renderLogin();
    await submitLogin("x@y.com", "WrongPass1!");

    await waitFor(() => expect(screen.getByText("Login failed")).toBeTruthy());
  });
});
