import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  AlertTriangle,
  BarChart3,
  ClipboardCheck,
  Settings,
  Columns3,
  LayoutDashboard,
  ListChecks,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Scale,
  Search,
  Sun,
  UserRound,
  LogOut,
  ChevronDown,
  Wallet,
} from "lucide-react";

import { useSession } from "@/features/auth/session";
import { canAdminister } from "@/lib/permissions";
import { applyTheme, cn, readStoredTheme, type Theme } from "@/lib/utils";

const NAV = [
  { to: "/", label: "nav.dashboard", icon: LayoutDashboard },
  { to: "/progetti", label: "nav.projects", icon: Columns3 },
  { to: "/wallet", label: "nav.wallet", icon: Wallet },
  { to: "/canone", label: "nav.canone", icon: Scale },
  { to: "/analisi-costi", label: "nav.costAnalysis", icon: BarChart3 },
  { to: "/riconciliazione", label: "nav.reconciliation", icon: ListChecks },
  { to: "/anomalie", label: "nav.anomalies", icon: AlertTriangle },
  { to: "/revisione", label: "nav.review", icon: ClipboardCheck },
] as const;

export function AppShell({ onOpenCommandPalette }: { onOpenCommandPalette: () => void }) {
  const { t } = useTranslation();
  const { session, signOut } = useSession();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("sl.sidebar.collapsed") === "true";
    } catch {
      return false;
    }
  });
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  useEffect(() => applyTheme(theme), [theme]);
  useEffect(() => {
    try {
      localStorage.setItem("sl.sidebar.collapsed", String(collapsed));
    } catch {
      /* storage unavailable */
    }
  }, [collapsed]);
  const currentPage =
    NAV.find(({ to }) => to !== "/" && location.pathname.startsWith(to))?.label ??
    (location.pathname === "/amministrazione" ? "Amministrazione" : "nav.dashboard");

  return (
    <div className="flex h-full">
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-border bg-card transition-[width]",
          collapsed ? "w-16" : "w-16 md:w-64",
        )}
      >
        <div className="flex h-16 items-center gap-3 border-b border-border px-4">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-sm font-bold text-accent-foreground">
            SL
          </span>
          {!collapsed && (
            <span className="hidden truncate text-sm font-semibold tracking-tight md:block">
              {t("app.name")}
            </span>
          )}
        </div>

        <nav className="flex-1 space-y-0.5 p-2" aria-label={t("app.name")}>
          {NAV.map(({ to, label, icon: Icon }, index) => (
            <div key={to}>
              {(index === 0 || index === 1 || index === 4) && !collapsed && (
                <p className="hidden px-2.5 pb-2 pt-5 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground md:block">
                  {index === 0 ? "Overview" : index === 1 ? "Gestione" : "Controllo"}
                </p>
              )}
              <NavLink
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
                title={t(label)}
                aria-label={t(label)}
              >
                <Icon className="size-4 shrink-0" aria-hidden />
                {!collapsed && <span className="hidden truncate md:block">{t(label)}</span>}
              </NavLink>
            </div>
          ))}
          {canAdminister(session) && (
            <NavLink
              to="/amministrazione"
              title="Amministrazione"
              aria-label="Amministrazione"
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition",
                  isActive
                    ? "bg-accent-subtle font-medium text-accent"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              <Settings className="size-4 shrink-0" aria-hidden />
              {!collapsed && <span className="hidden md:block">Amministrazione</span>}
            </NavLink>
          )}
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
              <span className="hidden md:block">Riduci</span>
            </>
          )}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center gap-3 border-b border-border bg-card/50 px-4 md:px-7">
          <div className="hidden min-w-40 text-sm font-medium text-foreground lg:block">
            {t(currentPage)}
          </div>
          <button
            type="button"
            onClick={onOpenCommandPalette}
            className="flex h-9 flex-1 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm text-muted-foreground hover:bg-muted md:max-w-md"
          >
            <Search className="size-4" aria-hidden />
            <span className="truncate">{t("app.commandPalette")}</span>
            <kbd className="ml-auto hidden shrink-0 whitespace-nowrap rounded border border-border px-1.5 font-mono text-2xs md:inline">
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

          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button
                type="button"
                aria-label="Menu account"
                className="flex h-9 items-center gap-2 rounded-md border border-input px-2 text-sm hover:bg-muted"
              >
                <UserRound className="size-4" aria-hidden />
                <span className="hidden max-w-32 truncate sm:inline">
                  {session?.full_name || session?.username}
                </span>
                <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end"
                sideOffset={6}
                className="z-50 min-w-48 rounded-lg border border-border bg-card p-1 text-sm shadow-raised"
              >
                <DropdownMenu.Label className="px-3 py-2 text-xs text-muted-foreground">
                  {session?.username}
                </DropdownMenu.Label>
                <DropdownMenu.Separator className="my-1 h-px bg-border" />
                <DropdownMenu.Item
                  onSelect={() => void signOut()}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 outline-none focus:bg-muted"
                >
                  <LogOut className="size-4" aria-hidden />
                  {t("auth.signOut")}
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </header>

        <main className="min-h-0 flex-1 overflow-auto p-4 md:p-7">
          <div className="mx-auto w-full max-w-[1600px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
