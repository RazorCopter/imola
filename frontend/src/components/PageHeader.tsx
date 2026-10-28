import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
      <div className="min-w-0 max-w-3xl">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-accent">
          {eyebrow}
        </p>
        <h1 className="break-words text-3xl font-semibold tracking-tight">{title}</h1>
        {description && <div className="mt-2 text-sm text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function FilterBar({ children, label = "Filtri" }: { children: ReactNode; label?: string }) {
  return (
    <div
      aria-label={label}
      className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-3"
    >
      {children}
    </div>
  );
}
