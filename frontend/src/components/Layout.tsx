import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { post, tokenStore } from "@/lib/api";
import clsx from "clsx";

const navByRole: Record<string, { to: string; label: string }[]> = {
  homeowner: [
    { to: "/quiz", label: "Style Quiz" },
    { to: "/recommendations", label: "Recommendations" },
    { to: "/moodboards", label: "Moodboards" },
    { to: "/floorplan", label: "Floorplan" },
    { to: "/shopping-list", label: "Shopping List" },
  ],
  designer: [
    { to: "/designer/dashboard", label: "Projects" },
    { to: "/quiz", label: "New Quiz" },
    { to: "/recommendations", label: "Recommendations" },
  ],
  admin: [
    { to: "/admin/products", label: "Products" },
    { to: "/admin/users", label: "Users" },
    { to: "/admin/subscriptions", label: "Subscriptions" },
  ],
};

export default function Layout() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  async function handleLogout() {
    try {
      const refresh = tokenStore.refresh;
      if (refresh) await post("/auth/logout", { refresh_token: refresh });
    } catch {
      /* logout is idempotent */
    }
    logout();
    navigate("/login");
  }

  const links = user ? (navByRole[user.role] ?? []) : [];

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-[#eee7db] bg-cream/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2 font-bold text-walnut">
            <span aria-hidden className="grid h-7 w-7 place-items-center rounded-lg bg-clay text-sm text-white">SD</span>
            Smart Decor
          </Link>
          <nav className="hidden gap-1 md:flex" aria-label="Main">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  clsx(
                    "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive ? "bg-sand text-walnut" : "text-stone hover:text-ink",
                  )
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            {user ? (
              <>
                {user.subscription_active && (
                  <span className="rounded-full bg-[#f7e3d9] px-2.5 py-0.5 text-xs font-semibold text-clay-dark">PRO</span>
                )}
                <span className="hidden text-sm text-stone sm:inline">{user.email}</span>
                <button
                  onClick={handleLogout}
                  className="rounded-lg px-3 py-1.5 text-sm font-medium text-stone hover:bg-sand hover:text-ink"
                >
                  Log out
                </button>
              </>
            ) : (
              <Link to="/login" className="rounded-lg bg-clay px-4 py-1.5 text-sm font-semibold text-white hover:bg-clay-dark">
                Sign in
              </Link>
            )}
          </div>
        </div>
        {links.length > 0 && (
          <nav className="flex gap-1 overflow-x-auto border-t border-[#eee7db] px-3 py-1.5 md:hidden" aria-label="Mobile">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  clsx(
                    "whitespace-nowrap rounded-lg px-3 py-1 text-xs font-medium",
                    isActive ? "bg-sand text-walnut" : "text-stone",
                  )
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
