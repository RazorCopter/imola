import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AppShell } from "@/components/AppShell";
import { CommandPalette } from "@/components/CommandPalette";
import { LoginPage } from "@/features/auth/LoginPage";
import { SessionExpiredDialog } from "@/features/auth/SessionExpiredDialog";
import { useSession } from "@/features/auth/session";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { CanonePage } from "@/features/canone/CanonePage";
import { ProjectDetailPage } from "@/features/projects/ProjectDetailPage";
import { ProjectsPage } from "@/features/projects/ProjectsPage";
import { WalletPage } from "@/features/wallet/WalletPage";
import { PlaceholderPage } from "@/components/PlaceholderPage";

export default function App() {
  const { status } = useSession();
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
      <Routes>
        <Route element={<AppShell onOpenCommandPalette={() => setPaletteOpen(true)} />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/progetti" element={<ProjectsPage />} />
          <Route path="/progetti/:projectId" element={<ProjectDetailPage />} />
          <Route path="/wallet" element={<WalletPage />} />
          <Route path="/canone" element={<CanonePage />} />
          <Route
            path="/riconciliazione"
            element={<PlaceholderPage titleKey="nav.reconciliation" />}
          />
          <Route path="/anomalie" element={<PlaceholderPage titleKey="nav.anomalies" />} />
          <Route path="/revisione" element={<PlaceholderPage titleKey="nav.review" />} />
          <Route path="/amministrazione" element={<PlaceholderPage titleKey="nav.admin" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <SessionExpiredDialog />
    </>
  );
}
