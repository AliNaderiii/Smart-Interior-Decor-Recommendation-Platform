/** Unit tests for the admin Users page delete control (P4-B).
 *
 * Backend contract under test: `DELETE /admin/users/{id}` → 200 receipt,
 * 409 with a specific sentence for self-deletion / last-admin, 404 unknown.
 * The page must (1) never offer the control for the caller's own row,
 * (2) ask for confirmation with the exact wording in `deleteConfirmMessage`,
 * (3) call the API only after confirmation, (4) surface the backend's 409
 * sentence verbatim instead of a generic failure.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getMock, delMock, patchMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  delMock: vi.fn(),
  patchMock: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>();
  return { ...orig, get: getMock, del: delMock, patch: patchMock };
});

import { ApiError } from "@/lib/api";
import { ToastProvider } from "@/components/Toast";
import { deleteConfirmMessage } from "@/lib/adminUsers";
import AdminUsersPage from "@/pages/admin/UsersPage";
import { useAuthStore } from "@/stores/authStore";
import { renderWithProviders } from "./renderWithProviders";

const ADMIN = {
  id: "admin-1",
  email: "admin@smartdecor.dev",
  full_name: "Admin",
  role: "admin" as const,
  is_active: true,
  subscription_active: false,
  subscription_plan: "free",
};

const ROWS = [
  { ...ADMIN, created_at: "2026-01-01T00:00:00Z" },
  {
    id: "probe-1",
    email: "probe-1788726950@example.com",
    full_name: "Probe",
    role: "homeowner",
    is_active: true,
    subscription_plan: "free",
    subscription_active: false,
    created_at: "2026-09-01T00:00:00Z",
  },
];

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return renderWithProviders(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <AdminUsersPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function probeRow() {
  const cell = await screen.findByText("probe-1788726950@example.com");
  return cell.closest("tr") as HTMLTableRowElement;
}

describe("AdminUsersPage — delete", () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({ user: ADMIN });
    getMock.mockReset();
    delMock.mockReset();
    patchMock.mockReset();
    getMock.mockResolvedValue(ROWS);
  });

  it("offers Delete for other accounts but never for the caller's own row", async () => {
    renderPage();
    const probe = await probeRow();
    expect(within(probe).getByRole("button", { name: /delete probe-1788726950@example\.com/i })).toBeTruthy();

    const own = screen.getByText("admin@smartdecor.dev").closest("tr") as HTMLTableRowElement;
    expect(within(own).queryByRole("button", { name: /delete/i })).toBeNull();
    expect(within(own).getByText("(you)")).toBeTruthy();
  });

  it("does nothing when the confirmation is declined", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();
    const probe = await probeRow();
    await userEvent.click(within(probe).getByRole("button", { name: /delete probe/i }));

    expect(confirm).toHaveBeenCalledWith(deleteConfirmMessage(ROWS[1]));
    expect(confirm.mock.calls[0][0]).toMatch(/permanently delete probe-1788726950@example\.com/i);
    expect(delMock).not.toHaveBeenCalled();
  });

  it("calls DELETE /admin/users/{id} after confirmation and reports the receipt", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    delMock.mockResolvedValue({
      id: "probe-1",
      audit_pseudonym: "erased-abc",
      email_pseudonym: "p***@example.com#1234",
      audit_rows_pseudonymised: 3,
      redis_keys_purged: 0,
    });
    renderPage();
    const probe = await probeRow();
    await userEvent.click(within(probe).getByRole("button", { name: /delete probe/i }));

    await waitFor(() => expect(delMock).toHaveBeenCalledWith("/admin/users/probe-1"));
    expect(await screen.findByText(/probe-1788726950@example\.com deleted/i)).toBeTruthy();
    expect(screen.getByText(/erased-abc/)).toBeTruthy();
    // The list is refetched so the row disappears from the server's answer.
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(2));
  });

  it("surfaces the backend's 409 sentence verbatim", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const sentence = "Refusing to remove the last active administrator";
    delMock.mockRejectedValue(new ApiError(409, sentence));
    renderPage();
    const probe = await probeRow();
    await userEvent.click(within(probe).getByRole("button", { name: /delete probe/i }));

    expect(await screen.findByText(sentence)).toBeTruthy();
    expect(screen.queryByText(/could not delete/i)).toBeNull();
  });

  it("falls back to a generic message for unexpected failures", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    delMock.mockRejectedValue(new ApiError(500, "boom"));
    renderPage();
    const probe = await probeRow();
    await userEvent.click(within(probe).getByRole("button", { name: /delete probe/i }));

    expect(await screen.findByText(/could not delete probe-1788726950@example\.com/i)).toBeTruthy();
  });

  it("filters the table by e-mail or name", async () => {
    renderPage();
    await probeRow();
    await userEvent.type(screen.getByLabelText(/filter by e-mail or name/i), "example.com");
    expect(screen.queryByText("admin@smartdecor.dev")).toBeNull();
    expect(screen.getByText("probe-1788726950@example.com")).toBeTruthy();
    expect(screen.getByText(/1 shown/)).toBeTruthy();
  });
});
