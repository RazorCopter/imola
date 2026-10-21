import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api } from "@/lib/api";
import { formatDays, formatDelta, formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

interface WalletBalance {
  anno: number;
  allocato: string;
  consumato: string;
  disponibile: string;
  disponibile_da_allocazioni: string;
  disponibile_da_allocazioni_aperte: string;
  capienza_wallet_potenziale: string;
  residui_validi_non_allocati: string;
  residui_in_scadenza: string;
  budget_residuo_progetti_in_corso: string;
  sforamenti_progetti_in_corso: string;
  residui_scaduti: string;
  residui_potenziali_da_verificare: string;
}

interface ReconciliationSummary {
  riepilogo: {
    righe: number;
    ok: number;
    ko: number;
    assenti_in_ppm: number;
    delta_totale: string;
    percentuale_allineati: string;
    snapshot_estratto_il: string | null;
  };
}

function KpiCard({
  label,
  value,
  hint,
  tone = "neutral",
  tooltip,
  action,
}: {
  label: string;
  value: string;
  hint?: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "danger";
  tooltip?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-subtle" title={tooltip}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        {tooltip !== undefined && (
          <span
            className="cursor-help text-xs text-muted-foreground hover:text-foreground"
            aria-label={tooltip}
          >
            ⓘ
          </span>
        )}
      </div>
      <p
        className={cn(
          "mt-2 font-mono text-2xl font-semibold tabular-nums",
          tone === "ok" && "text-ok",
          tone === "warn" && "text-warn",
          tone === "danger" && "text-danger",
        )}
      >
        {value}
      </p>
      {hint !== undefined && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
      {action !== undefined && <div className="mt-2 text-xs font-medium">{action}</div>}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="skeleton h-3 w-24" />
      <div className="skeleton mt-3 h-7 w-32" />
    </div>
  );
}

export function DashboardPage() {
  const { t } = useTranslation();
  const year = new Date().getFullYear();

  const wallet = useQuery({
    queryKey: ["wallet", "balance", year],
    queryFn: () => api.get<WalletBalance>(`/wallet/${year}/balance`),
  });
  const reconciliation = useQuery({
    queryKey: ["reconciliation", "latest"],
    queryFn: () => api.get<ReconciliationSummary>("/reconciliation/latest"),
  });

  const loading = wallet.isLoading || reconciliation.isLoading;

  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold tracking-tight">{t("dashboard.title")}</h1>
        <p className="text-sm text-muted-foreground">
          {t("wallet.available")} {year}
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {loading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <KpiCard
              label={t("wallet.available")}
              value={formatDays(wallet.data?.disponibile)}
              hint={`${t("wallet.allocated")} ${formatDays(wallet.data?.allocato)} · ${t(
                "wallet.consumed",
              )} ${formatDays(wallet.data?.consumato)}`}
              tooltip={`Disponibile = allocato (${formatDays(wallet.data?.allocato)}) − consumato (${formatDays(wallet.data?.consumato)}) = ${formatDays(wallet.data?.disponibile)}`}
              tone="ok"
            />
            <KpiCard
              label={t("wallet.ongoingBudget")}
              value={formatDays(wallet.data?.budget_residuo_progetti_in_corso)}
              hint={`Separato dal wallet · ${t("wallet.ongoingOverrun")}: ${formatDays(wallet.data?.sforamenti_progetti_in_corso)}`}
              tooltip={`Budget residuo progetti in corso al netto dei rilasci al wallet. Sforamenti: ${formatDays(wallet.data?.sforamenti_progetti_in_corso)}`}
              tone="neutral"
            />
            <KpiCard
              label={t("wallet.potential")}
              value={formatDays(wallet.data?.residui_potenziali_da_verificare)}
              hint="Esclusi dal disponibile ufficiale"
              tooltip="12 progetti da verificare o chiusi senza data; non spendibili finché non chiariti"
              action={
                <Link
                  to="/revisione"
                  className="text-primary inline-flex items-center underline underline-offset-4 hover:opacity-80"
                >
                  {t("wallet.reviewQueueLink")} &rarr;
                </Link>
              }
              tone="warn"
            />
            <KpiCard
              label={t("dashboard.reconciliationDelta")}
              value={formatDelta(reconciliation.data?.riepilogo.delta_totale)}
              hint={
                reconciliation.data?.riepilogo.snapshot_estratto_il
                  ? `${t("dashboard.lastSnapshot")}: ${new Date(
                      reconciliation.data.riepilogo.snapshot_estratto_il,
                    ).toLocaleDateString("it-IT")}`
                  : t("app.empty")
              }
              tooltip="Differenza consuntivi interni vs ultimo estratto PPM fornitore"
              tone={reconciliation.data?.riepilogo.ko ? "danger" : "ok"}
            />
          </>
        )}
      </div>

      {reconciliation.data !== undefined && (
        <div className="rounded-lg border border-border bg-card p-4 text-sm">
          <h2 className="font-medium">{t("nav.reconciliation")}</h2>
          <p className="mt-1 text-muted-foreground">
            {reconciliation.data.riepilogo.righe} righe ·{" "}
            <span className="text-ok">{reconciliation.data.riepilogo.ok} OK</span> ·{" "}
            <span className="text-danger">{reconciliation.data.riepilogo.ko} KO</span> ·{" "}
            {reconciliation.data.riepilogo.assenti_in_ppm} assenti in PPM ·{" "}
            {formatPercent(reconciliation.data.riepilogo.percentuale_allineati)} allineati
          </p>
        </div>
      )}
    </section>
  );
}
