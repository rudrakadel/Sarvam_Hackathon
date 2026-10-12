/**
 * VeriDictum AI — Root Application Router
 *
 * Every page is loaded via React.lazy so the initial bundle ships only the
 * router + auth store + error boundary. Heavy pages (NL Query with Vera glow,
 * Case Detail with Recharts + timeline) load on first navigation.
 *
 * The Suspense fallback shows the Skeleton shimmer so the UX is "loading
 * gracefully" rather than "stuck on a white screen during chunk fetch".
 */

import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider, MutationCache, QueryCache } from "@tanstack/react-query";
import { Toaster, toast } from "react-hot-toast";
import { AxiosError } from "axios";
import { useAuthStore } from "@/store/authStore";

// Eagerly loaded shell — needed on every route, no lazy benefit.
import { Layout } from "@/components/organisms/Layout";
import { ErrorBoundary } from "@/components/organisms/ErrorBoundary";
import { Skeleton } from "@/components/atoms/Skeleton";
import { useTheme } from "@/hooks/useTheme";

// Helper that lifts named exports into the default slot React.lazy expects.
function lazyNamed<T extends Record<string, unknown>>(
  importer: () => Promise<T>,
  exportName: keyof T,
) {
  return lazy(() =>
    importer().then((mod) => ({ default: mod[exportName] as React.ComponentType<unknown> })),
  );
}

// ── Auth pages (small, but still chunked separately) ────────────────────────
const LoginPage          = lazyNamed(() => import("@/pages/auth/LoginPage"),          "LoginPage");
const RegisterPage       = lazyNamed(() => import("@/pages/auth/RegisterPage"),       "RegisterPage");
const ForgotPasswordPage = lazyNamed(() => import("@/pages/auth/ForgotPasswordPage"), "ForgotPasswordPage");
const ResetPasswordPage  = lazyNamed(() => import("@/pages/auth/ResetPasswordPage"),  "ResetPasswordPage");

// ── App pages — heaviest first so we can see the chunks separating ─────────
const DashboardPage         = lazyNamed(() => import("@/pages/dashboard/DashboardPage"),       "DashboardPage");
const CasesListPage         = lazyNamed(() => import("@/pages/cases/CasesListPage"),           "CasesListPage");
const CaseDetailPage        = lazyNamed(() => import("@/pages/cases/CaseDetailPage"),          "CaseDetailPage");
const NewCasePage           = lazyNamed(() => import("@/pages/cases/NewCasePage"),             "NewCasePage");
const AudioUploadPage       = lazyNamed(() => import("@/pages/transcripts/AudioUploadPage"),   "AudioUploadPage");
const TranscriptViewerPage  = lazyNamed(() => import("@/pages/transcripts/TranscriptViewerPage"), "TranscriptViewerPage");
const DocumentUploadPage    = lazyNamed(() => import("@/pages/documents/DocumentUploadPage"),  "DocumentUploadPage");
const NLQueryPage           = lazyNamed(() => import("@/pages/reports/NLQueryPage"),           "NLQueryPage");
const ReportsListPage       = lazyNamed(() => import("@/pages/reports/ReportsListPage"),       "ReportsListPage");
const SettingsPage          = lazyNamed(() => import("@/pages/settings/SettingsPage"),         "SettingsPage");

/**
 * Extract a user-friendly message from an Axios error. Falls back through
 * the standard layers: API-provided `detail` → status code → generic.
 */
function extractErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    const data: unknown = err.response?.data;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
    if (err.response?.status === 401) return "Your session has expired. Please log in again.";
    if (err.response?.status === 403) return "You don't have permission for that action.";
    if (err.response?.status === 404) return "Not found.";
    if (err.response?.status && err.response.status >= 500) {
      return "Something went wrong on the server. Please try again.";
    }
    if (err.code === "ERR_NETWORK") return "Can't reach the server. Check your connection.";
  }
  return "Something went wrong. Please try again.";
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
    mutations: {
      // Per-mutation `onError` callbacks still run; this is the safety net
      // for mutations that don't handle their own errors.
      retry: 0,
    },
  },
  // Global error handlers — every failed background fetch surfaces a toast
  // rather than failing silently. The 401 path is special-cased: the axios
  // interceptor in services/api.ts handles refresh automatically; only
  // surface a toast if the refresh ALSO failed.
  queryCache: new QueryCache({
    onError: (err, query) => {
      // Skip if the query author opted out (meta.silent: true)
      if (query.meta?.silent) return;
      // Skip first-load errors when the user just hasn't logged in yet —
      // routing will redirect them.
      if (err instanceof AxiosError && err.response?.status === 401) return;
      toast.error(extractErrorMessage(err), { id: `query-${query.queryHash}` });
    },
  }),
  mutationCache: new MutationCache({
    onError: (err, _vars, _ctx, mutation) => {
      if (mutation.meta?.silent) return;
      if (mutation.options.onError) return; // caller handles it
      toast.error(extractErrorMessage(err));
    },
  }),
});

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <Layout>{children}</Layout>
    </RequireAuth>
  );
}

/** Skeleton shown while a route chunk downloads. */
function RouteFallback() {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-4" aria-busy="true">
      <Skeleton className="h-7 w-48" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

export default function App() {
  // Side-effect only — applies the persisted theme to <html>. Called once
  // here so every page gets the theme without each page importing useTheme.
  useTheme();

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: { fontSize: "14px" },
            success: { iconTheme: { primary: "#16a34a", secondary: "#fff" } },
            error: { iconTheme: { primary: "#dc2626", secondary: "#fff" } },
          }}
        />
        <BrowserRouter>
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              {/* Public routes */}
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />

              {/* Protected routes */}
              <Route path="/dashboard"                                        element={<AppLayout><DashboardPage /></AppLayout>} />
              <Route path="/cases"                                            element={<AppLayout><CasesListPage /></AppLayout>} />
              <Route path="/cases/new"                                        element={<AppLayout><NewCasePage /></AppLayout>} />
              <Route path="/cases/:caseId"                                    element={<AppLayout><CaseDetailPage /></AppLayout>} />
              <Route path="/cases/:caseId/upload-audio"                       element={<AppLayout><AudioUploadPage /></AppLayout>} />
              <Route path="/cases/:caseId/audio/:audioId/transcripts/:transcriptId" element={<AppLayout><TranscriptViewerPage /></AppLayout>} />
              <Route path="/cases/:caseId/query"                              element={<AppLayout><NLQueryPage /></AppLayout>} />
              <Route path="/cases/:caseId/upload-document"                    element={<AppLayout><DocumentUploadPage /></AppLayout>} />
              <Route path="/reports"                                          element={<AppLayout><ReportsListPage /></AppLayout>} />
              <Route path="/settings"                                         element={<AppLayout><SettingsPage /></AppLayout>} />

              {/* Default redirect */}
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
