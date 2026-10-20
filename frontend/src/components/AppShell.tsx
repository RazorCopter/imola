import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ClipboardCheck,
  Columns3,
  LayoutDashboard,
  ListChecks,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Scale,
  Search,
  Settings,
  Sun,
  Wallet,
} from "lucide-react";

import { useSession } from "@/features/auth/session";
import { applyTheme, cn, readStoredTheme, type Theme } from "@/lib/utils";

const NAV = [
  { to: "/", label: "nav.dashboard", icon: LayoutDashboard },
  { to: "/progetti", label: "nav.projects", icon: Columns3 },
  { to: "/wallet", label: "nav.wallet", icon: Wallet },
  { to: "/canone", label: "nav.canone", icon: Scale },
  { to: "/riconciliazione", label: "nav.reconciliation", icon: ListChecks },
  { to: "/anomalie", label: "nav.anomalies", icon: AlertTriangle },
  { to: "/revisione", label: "nav.review", icon: ClipboardCheck },
  { to: "/amministrazione", label: "nav.admin", icon: Settings },
] as const;

export function AppShell({ onOpenCommandPalette }: { onOpenCommandPalette: () => void }) {
  const { t } = useTranslation();
  const { session, signOut } = useSession();
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  useEffect(() => applyTheme(theme), [theme]);

  return (
    <div className="flex h-full">
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-border bg-card transition-[width]",
          collapsed ? "w-14" : "w-60",
        )}
      >
        <div className="flex h-14 items-center gap-2 border-b border-border px-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-accent text-sm font-semibold text-accent-foreground">
            SL
          </span>
          {!collapsed && <span className="truncate text-sm font-semibold">{t("app.name")}</span>}
        </div>

        <nav className="flex-1 space-y-0.5 p-2" aria-label={t("app.name")}>
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition",
                  isActive
                    ? "bg-accent-subtle font-medium text-accent"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
              title={collapsed ? t(label) : undefined}
            >
              <Icon className="size-4 shrink-0" aria-hidden />
              {!collapsed && <span className="truncate">{t(label)}</span>}
            </NavLink>
          ))}
        </nav>

        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          className="m-2 flex items-center gap-2 rounded-md px-2.5 py-2 text-sm text-muted-foreground hover:bg-muted"
          aria-label={collapsed ? "Espandi il menu" : "Riduci il menu"}
        >
          {collapsed ? (
            <PanelLeftOpen className="size-4" aria-hidden />
          ) : (
            <>
              <PanelLeftClose className="size-4" aria-hidden />
              <span>Riduci</span>
            </>
          )}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-border px-4">
          <button
            type="button"
            onClick={onOpenCommandPalette}
            className="flex h-9 flex-1 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm text-muted-foreground hover:bg-muted md:max-w-md"
          >
            <Search className="size-4" aria-hidden />
            <span className="truncate">{t("app.commandPalette")}</span>
            <kbd className="ml-auto hidden rounded border border-border px-1.5 font-mono text-2xs md:inline">
              Ctrl K
            </kbd>
          </button>

          <button
            type="button"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="flex size-9 items-center justify-center rounded-md border border-input hover:bg-muted"
            aria-label={theme === "dark" ? t("app.theme.light") : t("app.theme.dark")}
          >
            {theme === "dark" ? (
              <Sun className="size-4" aria-hidden />
            ) : (
              <Moon className="size-4" aria-hidden />
            )}
          </button>

          <div className="flex items-center gap-2">
            <span className="hidden text-sm text-muted-foreground sm:inline">
              {session?.full_name}
            </span>
            <button
              type="button"
              onClick={() => void signOut()}
              className="h-9 rounded-md border border-input px-3 text-sm hover:bg-muted"
            >
              {t("auth.signOut")}
            </button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-auto p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
