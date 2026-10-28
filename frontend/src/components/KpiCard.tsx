import type { ReactNode } from "react";

import { MetricLabel } from "@/components/InfoTooltip";
import { cn } from "@/lib/utils";

export function KpiCard({
  label,
  value,
  hint,
  tone = "neutral",
  tooltip,
  action,
  featured = false,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "danger";
  tooltip?: string;
  action?: ReactNode;
  featured?: boolean;
}) {
  return (
    <article
      className={cn(
        "relative min-w-0 rounded-xl border border-border bg-card p-5 shadow-subtle",
        featured && "border-accent/40 bg-accent-subtle/40 xl:col-span-2",
      )}
    >
      <MetricLabel label={label} description={tooltip ?? `Indicatore ${label}.`} />
      <div
        className={cn(
          "mt-3 text-2xl font-semibold tabular-nums tracking-tight",
          tone === "ok" && "text-ok",
          tone === "warn" && "text-warn",
          tone === "danger" && "text-danger",
        )}
      >
        {value}
      </div>
      {(hint || action) && (
        <div className="mt-2 flex flex-col items-start gap-2 text-xs text-muted-foreground">
          <span>{hint}</span>
          {action}
        </div>
      )}
    </article>
  );
}
