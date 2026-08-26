import type { ComponentType, ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { tokenStore, usingCookieAuth } from "@/lib/api";

export function RequireAuth({ children, roles }: { children: ReactNode; roles?: string[] }) {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  // Stage 1 (T-1.4): a session is established when the profile is known AND
  // the credentials live somewhere — a Bearer token in the token store, or
  // the backend's httpOnly-cookie pair (signalled by the readable
  // `csrf_token` cookie, see lib/api.usingCookieAuth). Requiring
  // `tokenStore.access` unconditionally bounced every valid cookie-mode
  // session (the DEFAULT, USE_COOKIE_AUTH=true) back to /login — the
  // authenticated half of the product was unreachable in that mode.
  // An expired cookie session is still handled: the first API call 401s,
  // the refresh flow in lib/api fails, and it redirects to /login.
  if (!user || (!tokenStore.access && !usingCookieAuth())) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

/** HOC paywall: renders the wrapped component only for active subscribers;
 *  otherwise shows the upgrade CTA overlay provided by the caller. */
export function withSubscription<P extends object>(
  Component: ComponentType<P>,
  Fallback: ComponentType<P>,
): ComponentType<P> {
  return function Guarded(props: P) {
    const user = useAuthStore((s) => s.user);
    if (user?.subscription_active) return <Component {...props} />;
    return <Fallback {...props} />;
  };
}
