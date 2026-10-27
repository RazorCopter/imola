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
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "danger";
  tooltip?: string;
  action?: ReactNode;
}) {
  return (
    <article className="rounded-lg border border-border bg-card p-4 shadow-subtle">
      <MetricLabel label={label} description={tooltip ?? `Indicatore ${label}.`} />
      <div
        className={cn(
          "mt-2 font-mono text-2xl font-semibold tabular-nums",
          tone === "ok" && "text-ok",
          tone === "warn" && "text-warn",
          tone === "danger" && "text-danger",
        )}
      >
        {value}
      </div>
      {(hint || action) && (
        <div className="mt-1 flex items-end justify-between gap-2 text-xs text-muted-foreground">
          <span>{hint}</span>
          {action}
        </div>
      )}
    </article>
  );
}
