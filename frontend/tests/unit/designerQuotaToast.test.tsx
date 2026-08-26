/** Unit tests for the designer quota wall's error display
 *  (Stage 1, T-1.4 close-out).
 *
 * The DOM-side twin of journey-designer.spec.ts. The backend refuses the
 * over-quota project with 402 and a specific, actionable Persian sentence
 * (app/services/designer_quota.py):
 *
 *   «سهمیهٔ پروژه‌های شما در پلن «طراح - رایگان» به پایان رسیده است
 *    (حداکثر 2 پروژه). برای ایجاد پروژه‌های بیشتر، اشتراک خود را ارتقا دهید.»
 *
 * The dashboard used to throw that away and always toast the generic English
 * "Could not create the project." — the designer was told nothing about why
 * they were blocked or what to do. Same defect class as the LoginPage one.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getMock, postMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  postMock: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/lib/api")>();
  return { ...orig, get: getMock, post: postMock };
});

import { ApiError } from "@/lib/api";
import { ToastProvider } from "@/components/Toast";
import DesignerDashboardPage from "@/pages/designer/DashboardPage";

/** Verbatim backend message (designer_quota.py QUOTA_MESSAGE, formatted). */
const QUOTA_MESSAGE =
  "سهمیهٔ پروژه‌های شما در پلن «طراح - رایگان» به پایان رسیده است " +
  "(حداکثر 2 پروژه). برای ایجاد پروژه‌های بیشتر، اشتراک خود را ارتقا دهید.";

function renderDashboard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <DesignerDashboardPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function submitNewProject(name = "Villa Lavasan") {
  await userEvent.click(await screen.findByRole("button", { name: /new project/i }));
  await userEvent.type(screen.getByLabelText(/project name/i), name);
  await userEvent.click(screen.getByRole("button", { name: /^create$/i }));
}

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  // Two existing projects — the designer_free quota is already used up.
  getMock.mockResolvedValue([]);
});

describe("designer quota wall", () => {
  it("surfaces the backend's Persian 402 message in the toast", async () => {
    postMock.mockRejectedValue(
      new ApiError(402, QUOTA_MESSAGE, { success: false, data: null, error: QUOTA_MESSAGE }),
    );
    renderDashboard();
    await submitNewProject();

    await waitFor(() => expect(screen.getByText(QUOTA_MESSAGE)).toBeTruthy());
    // The generic English string must NOT be what the designer sees.
    expect(screen.queryByText("Could not create the project.")).toBeNull();
  });

  it("announces the quota message in the live region so it is not silent", async () => {
    postMock.mockRejectedValue(new ApiError(402, QUOTA_MESSAGE));
    const { container } = renderDashboard();
    await submitNewProject();

    await waitFor(() => expect(screen.getByText(QUOTA_MESSAGE)).toBeTruthy());
    const live = container.querySelector('[role="status"][aria-live="polite"]');
    expect(live).not.toBeNull();
    expect(live?.textContent).toContain("سهمیهٔ پروژه‌های شما");
  });

  it("renders the server message as escaped text, never live HTML", async () => {
    const evil = '"><img src=x onerror="window.__xss_fired=true">';
    postMock.mockRejectedValue(new ApiError(402, evil));
    const { container } = renderDashboard();
    await submitNewProject();

    await waitFor(() => expect(screen.getByText(evil)).toBeTruthy());
    expect(container.querySelector('img[src="x"]')).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("falls back to the generic message for non-ApiError failures", async () => {
    postMock.mockRejectedValue(new TypeError("NetworkError: failed to fetch"));
    renderDashboard();
    await submitNewProject();

    await waitFor(() =>
      expect(screen.getByText("Could not create the project.")).toBeTruthy(),
    );
  });

  it("keeps the create dialog's data and does not claim success on 402", async () => {
    postMock.mockRejectedValue(new ApiError(402, QUOTA_MESSAGE));
    renderDashboard();
    await submitNewProject("Villa Lavasan");

    await waitFor(() => expect(screen.getByText(QUOTA_MESSAGE)).toBeTruthy());
    // No success toast alongside the failure.
    expect(screen.queryByText("Project created.")).toBeNull();
  });
});
