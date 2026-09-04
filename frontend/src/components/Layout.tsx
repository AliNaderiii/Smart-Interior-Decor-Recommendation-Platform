import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { post, tokenStore } from "@/lib/api";
import clsx from "clsx";
import { useThemeStore } from "@/stores/themeStore";
import { useCommandPalette } from "@/components/CommandPalette";
import { t } from "@/i18n/fa";

const navByRole: Record<string, { to: string; label: string }[]> = {
  homeowner: [
    { to: "/quiz", label: t.nav.quiz },
    { to: "/recommendations", label: t.nav.recommendations },
    { to: "/moodboards", label: t.nav.moodboards },
    { to: "/floorplan", label: t.nav.floorplan },
    { to: "/shopping-list", label: t.nav.shoppingList },
  ],
  designer: [
    { to: "/designer/dashboard", label: t.nav.designerDashboard },
    { to: "/quiz", label: t.nav.quiz },
    { to: "/recommendations", label: t.nav.recommendations },
  ],
  admin: [
    { to: "/admin/products", label: t.nav.adminProducts },
    { to: "/admin/users", label: t.nav.adminUsers },
    { to: "/admin/subscriptions", label: "اشتراک‌ها" },
  ],
};

/** Cmd+K is invisible to touch users and to anyone who does not already know
 *  the convention, so the palette also needs a visible affordance (RESEARCH_V2
 *  §6). This button is that affordance. */
function PaletteButton() {
  const { setOpen } = useCommandPalette();
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      aria-label={t.nav.openSearch}
      className="hidden items-center gap-2 rounded-lg border border-[var(--color-line)] px-2.5 py-1.5 text-xs text-[var(--color-muted)] transition-colors hover:border-[var(--color-faint)] hover:text-[var(--color-ink)] sm:flex"
    >
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
        <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <span>{t.nav.search}</span>
      <kbd className="rounded border border-[var(--color-line)] px-1 py-0.5 font-sans text-[10px]">
        {isMac ? "\u2318" : "Ctrl"}K
      </kbd>
    </button>
  );
}

function ThemeToggle() {
  const mode = useThemeStore((s) => s.mode);
  const toggle = useThemeStore((s) => s.toggle);
  const dark = mode === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? t.nav.lightMode : t.nav.darkMode}
      aria-pressed={dark}
      title={dark ? t.nav.lightMode : t.nav.darkMode}
      className="grid h-9 w-9 place-items-center rounded-lg text-[var(--color-muted)] transition-colors hover:bg-[var(--color-line)] hover:text-[var(--color-ink)]"
    >
      {dark ? (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.7" />
          <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.1 5.1l1.4 1.4M17.5 17.5l1.4 1.4M18.9 5.1l-1.4 1.4M6.5 17.5l-1.4 1.4"
                stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
      ) : (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M20 14.5A8.5 8.5 0 019.5 4a8.5 8.5 0 1010.5 10.5z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}

export default function Layout() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  async function handleLogout() {
    try {
      // Stage 03 (T-12): this used to be skipped whenever there was no token
      // in localStorage — which is exactly the cookie-auth case. The session
      // then survived "Sign out" completely: the httpOnly refresh cookie stayed
      // valid until it expired, and clearing local state only hid it. Always
      // tell the server, and let it revoke the token and expire the cookies.
      const refresh = tokenStore.refresh;
      await post("/auth/logout", refresh ? { refresh_token: refresh } : {});
    } catch {
      /* logout is idempotent — a failed call must never trap the user in */
    }
    logout();
    navigate("/login");
  }

  const links = user ? (navByRole[user.role] ?? []) : [];

  return (
    <div className="min-h-screen bg-[var(--color-canvas)]">
      {/* Keyboard users must be able to bypass the nav (WCAG 2.4.1). */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-[var(--color-accent)] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-[var(--color-canvas)]"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-[var(--color-line)] bg-[var(--color-canvas)]/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-[-0.02em] text-[var(--color-ink)]">
            <span aria-hidden className="grid h-7 w-7 place-items-center rounded-lg bg-[var(--color-accent)] text-sm text-[var(--color-canvas)]">SD</span>
            {t.brand}
          </Link>
          <nav className="hidden gap-1 md:flex" aria-label="Main">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  clsx(
                    "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-[var(--color-line)] text-[var(--color-ink)]"
                      : "text-[var(--color-muted)] hover:text-[var(--color-ink)]",
                  )
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            <PaletteButton />
            <ThemeToggle />
            {user ? (
              <>
                {user.subscription_active && (
                  <span className="rounded-full bg-[var(--color-accent)]/8 px-2.5 py-0.5 text-xs font-semibold text-[var(--color-accent)]">PRO</span>
                )}
                <span dir="ltr" className="hidden text-sm text-[var(--color-muted)] lg:inline">{user.email}</span>
                <button
                  onClick={handleLogout}
                  className="rounded-lg px-3 py-1.5 text-sm font-medium text-[var(--color-muted)] hover:bg-[var(--color-line)] hover:text-[var(--color-ink)]"
                >
                  {t.nav.logout}
                </button>
              </>
            ) : (
              <Link to="/login" className="rounded-xl bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-[var(--color-canvas)] hover:opacity-90">
                {t.nav.login}
              </Link>
            )}
          </div>
        </div>
        {links.length > 0 && (
          <nav className="flex gap-1 overflow-x-auto border-t border-[var(--color-line)] px-3 py-1.5 md:hidden" aria-label="ناوبری موبایل">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  clsx(
                    "whitespace-nowrap rounded-lg px-3 py-1 text-xs font-medium",
                    isActive ? "bg-[var(--color-line)] text-[var(--color-ink)]" : "text-[var(--color-muted)]",
                  )
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-12">
        <Outlet />
      </main>
    </div>
  );
}
