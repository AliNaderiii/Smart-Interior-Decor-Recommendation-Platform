import type { ComponentType, ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { tokenStore } from "@/lib/api";

export function RequireAuth({ children, roles }: { children: ReactNode; roles?: string[] }) {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  if (!user || !tokenStore.access) {
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
