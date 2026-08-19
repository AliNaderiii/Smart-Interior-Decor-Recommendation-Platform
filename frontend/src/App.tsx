import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Layout from "@/components/Layout";
import { RequireAuth } from "@/components/guards";
import { Spinner } from "@/components/ui";
import HomePage from "@/pages/HomePage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import QuizPage from "@/pages/QuizPage";
import RecommendationsPage from "@/pages/RecommendationsPage";

// Route-level code splitting keeps the recommendation page bundle lean (LCP).
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

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<Spinner />}>
          <Routes>
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
      </BrowserRouter>
    </QueryClientProvider>
  );
}
