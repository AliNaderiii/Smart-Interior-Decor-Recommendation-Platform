import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Layout from "@/components/Layout";
import { RequireAuth } from "@/components/guards";
import { Spinner } from "@/components/ui";
import { ToastProvider } from "@/components/Toast";
import { CommandPaletteProvider } from "@/components/CommandPalette";
import HomePage from "@/pages/HomePage";
import LoginPage from "@/pages/LoginPage";

// Perf (V2 Phase 2): every route below is auth-gated, so none of it can be
// the first paint — an anonymous visitor always lands on /, /login or a
// /share link. Keeping Quiz + Recommendations eager cost ~4 KB gzip in the
// entry chunk for code no logged-out user can reach.

// Register is lazy too: an anonymous visitor's first paint is always "/" or
// "/login" (or a "/share/:token" link). Reaching /register requires a click,
// by which time the chunk has already been fetched in the background.
const RegisterPage = lazy(() => import("@/pages/RegisterPage"));

// Route-level code splitting keeps the recommendation page bundle lean (LCP).
const QuizPage = lazy(() => import("@/pages/QuizPage"));
const RecommendationsPage = lazy(() => import("@/pages/RecommendationsPage"));
const MoodboardsPage = lazy(() => import("@/pages/MoodboardsPage"));
const MoodboardEditorPage = lazy(() => import("@/pages/MoodboardEditorPage"));
const FloorplanPage = lazy(() => import("@/pages/FloorplanPage"));
const ShoppingListPage = lazy(() => import("@/pages/ShoppingListPage"));
const UpgradePage = lazy(() => import("@/pages/UpgradePage"));
const SharePage = lazy(() => import("@/pages/SharePage"));
const DesignerDashboardPage = lazy(() => import("@/pages/designer/DashboardPage"));
const DesignerProjectPage = lazy(() => import("@/pages/designer/ProjectPage"));
const AdminProductsPage = lazy(() => import("@/pages/admin/ProductsPage"));
const AdminUsersPage = lazy(() => import("@/pages/admin/UsersPage"));
const AdminSubscriptionsPage = lazy(() => import("@/pages/admin/SubscriptionsPage"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

/** Page transition: fade + 20px rise (DESIGN_SYSTEM_V2 §4).
 *
 *  Done in CSS, not Framer Motion. Keying the wrapper on pathname remounts it
 *  per route, which restarts the `page-enter` animation — same visual result as
 *  AnimatePresence for an enter-only transition, at zero JS cost on the
 *  critical path. (Framer's core is ~35 KB gzip; the initial-JS budget is
 *  120 KB. See src/index.css for the full rationale.) */
function AnimatedRoutes() {
  const location = useLocation();
  return (
    <>
      <div key={location.pathname} className="page-enter">
        <Suspense fallback={<Spinner />}>
          <Routes location={location}>
            <Route element={<Layout />}>
              <Route path="/" element={<HomePage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/share/:token" element={<SharePage />} />

              <Route path="/quiz" element={<RequireAuth><QuizPage /></RequireAuth>} />
              <Route path="/recommendations" element={<RequireAuth><RecommendationsPage /></RequireAuth>} />
              <Route path="/moodboards" element={<RequireAuth><MoodboardsPage /></RequireAuth>} />
              <Route path="/moodboard/:id" element={<RequireAuth><MoodboardEditorPage /></RequireAuth>} />
              <Route path="/floorplan" element={<RequireAuth><FloorplanPage /></RequireAuth>} />
              <Route path="/shopping-list" element={<RequireAuth><ShoppingListPage /></RequireAuth>} />
              <Route path="/upgrade" element={<RequireAuth><UpgradePage /></RequireAuth>} />

              <Route path="/designer/dashboard" element={<RequireAuth roles={["designer", "admin"]}><DesignerDashboardPage /></RequireAuth>} />
              <Route path="/designer/project/:id" element={<RequireAuth roles={["designer", "admin"]}><DesignerProjectPage /></RequireAuth>} />

              <Route path="/admin/products" element={<RequireAuth roles={["admin"]}><AdminProductsPage /></RequireAuth>} />
              <Route path="/admin/users" element={<RequireAuth roles={["admin"]}><AdminUsersPage /></RequireAuth>} />
              <Route path="/admin/subscriptions" element={<RequireAuth roles={["admin"]}><AdminSubscriptionsPage /></RequireAuth>} />
            </Route>
          </Routes>
        </Suspense>
      </div>
    </>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/* Palette needs a Router (it navigates); Toast wraps everything so any
            page can report success/failure. */}
        <CommandPaletteProvider>
          <ToastProvider>
            <AnimatedRoutes />
          </ToastProvider>
        </CommandPaletteProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
