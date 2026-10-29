import { Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AppShell } from "@/components/AppShell";
import { CommandPalette } from "@/components/CommandPalette";
import { canAdminister } from "@/lib/permissions";
import { LoadingState } from "@/components/UiState";
import { LoginPage } from "@/features/auth/LoginPage";
import { SessionExpiredDialog } from "@/features/auth/SessionExpiredDialog";
import { useSession } from "@/features/auth/session";

const ManagementReportPage = lazy(() =>
  import("@/features/report/ManagementReportPage").then((m) => ({
    default: m.ManagementReportPage,
  })),
);

const DashboardPage = lazy(() =>
  import("@/features/dashboard/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);
const AnomaliesPage = lazy(() =>
  import("@/features/anomalies/AnomaliesPage").then((m) => ({ default: m.AnomaliesPage })),
);
const ReconciliationPage = lazy(() =>
  import("@/features/reconciliation/ReconciliationPage").then((m) => ({
    default: m.ReconciliationPage,
  })),
);
const CanonePage = lazy(() =>
  import("@/features/canone/CanonePage").then((m) => ({ default: m.CanonePage })),
);
const ProjectDetailPage = lazy(() =>
  import("@/features/projects/ProjectDetailPage").then((m) => ({ default: m.ProjectDetailPage })),
);
const ProjectsPage = lazy(() =>
  import("@/features/projects/ProjectsPage").then((m) => ({ default: m.ProjectsPage })),
);
const WalletPage = lazy(() =>
  import("@/features/wallet/WalletPage").then((m) => ({ default: m.WalletPage })),
);
const ReviewQueuePage = lazy(() =>
  import("@/features/review/ReviewQueuePage").then((m) => ({ default: m.ReviewQueuePage })),
);
const AdminPage = lazy(() =>
  import("@/features/admin/AdminPage").then((m) => ({ default: m.AdminPage })),
);
const CostAnalysisPage = lazy(() =>
  import("@/features/cost-analysis/CostAnalysisPage").then((m) => ({
    default: m.CostAnalysisPage,
  })),
);

export default function App() {
  const { status, session } = useSession();
  const { t } = useTranslation();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  if (status === "loading") {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        {t("app.loading")}
      </div>
    );
  }

  if (status === "anonymous") {
    return <LoginPage />;
  }

  return (
    <>
      <Suspense fallback={<LoadingState />}>
        <Routes>
          <Route
            path="/report-gestionale"
            element={
              session?.is_admin || session?.roles.includes("admin") ? (
                <ManagementReportPage />
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
          <Route element={<AppShell onOpenCommandPalette={() => setPaletteOpen(true)} />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/progetti" element={<ProjectsPage />} />
            <Route path="/progetti/:projectId" element={<ProjectDetailPage />} />
            <Route path="/wallet" element={<WalletPage />} />
            <Route path="/canone" element={<CanonePage />} />
            <Route path="/analisi-costi" element={<CostAnalysisPage />} />
            <Route path="/riconciliazione" element={<ReconciliationPage />} />
            <Route path="/anomalie" element={<AnomaliesPage />} />
            <Route path="/revisione" element={<ReviewQueuePage />} />
            <Route
              path="/amministrazione"
              element={canAdminister(session) ? <AdminPage /> : <Navigate to="/" replace />}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <SessionExpiredDialog />
    </>
  );
}
