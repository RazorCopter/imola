import type { ReactNode } from "react";

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
    <article className="rounded-lg border border-border bg-card p-4 shadow-subtle" title={tooltip}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        {tooltip && (
          <span className="cursor-help text-xs text-muted-foreground" aria-label={tooltip}>
            ⓘ
          </span>
        )}
      </div>
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
