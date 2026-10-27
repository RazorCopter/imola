interface InfoTooltipProps {
  label: string;
  description: string;
}

export function InfoTooltip({ label, description }: InfoTooltipProps) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-label={`Informazioni su ${label}`}
        className="hover:border-primary focus-visible:outline-primary inline-flex size-5 items-center justify-center rounded-full border border-border bg-background text-xs font-bold text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        ?
      </button>
      <span
        role="tooltip"
        className="bg-popover text-popover-foreground pointer-events-none absolute right-0 top-7 z-50 hidden w-72 rounded-md border border-border p-3 text-left text-xs font-normal normal-case tracking-normal shadow-lg group-focus-within:block group-hover:block"
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
