import { useId } from "react";

interface InfoTooltipProps {
  label: string;
  description: string;
}

export function InfoTooltip({ label, description }: InfoTooltipProps) {
  const tooltipId = useId();
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={`Informazioni su ${label}`}
        aria-describedby={tooltipId}
        className="inline-flex size-5 items-center justify-center rounded-full border border-border bg-background text-xs font-bold text-muted-foreground hover:border-primary hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        ?
      </button>
      <span
        role="tooltip"
        id={tooltipId}
        className="pointer-events-none absolute right-0 top-7 z-50 hidden w-72 rounded-md border border-slate-700 bg-slate-950 p-3 text-left text-xs font-normal normal-case tracking-normal text-slate-50 opacity-100 shadow-2xl group-focus-within:block group-hover:block"
      >
        {description}
      </span>
    </span>
  );
}

export function MetricLabel({ label, description }: InfoTooltipProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <InfoTooltip label={label} description={description} />
    </div>
  );
}
