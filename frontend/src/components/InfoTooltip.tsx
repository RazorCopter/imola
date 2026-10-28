import * as Tooltip from "@radix-ui/react-tooltip";
interface InfoTooltipProps {
  label: string;
  description: string;
}
export function InfoTooltip({ label, description }: InfoTooltipProps) {
  return (
    <Tooltip.Provider delayDuration={250}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button
            type="button"
            aria-label={`Informazioni su ${label}`}
            className="inline-flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-background text-xs font-bold text-muted-foreground hover:border-primary hover:text-foreground"
          >
            ?
          </button>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            sideOffset={8}
            align="end"
            collisionPadding={12}
            className="z-[100] max-w-[min(18rem,calc(100vw-2rem))] rounded-md border border-slate-700 bg-slate-950 p-3 text-left text-xs font-normal normal-case tracking-normal text-slate-50 opacity-100 shadow-2xl"
          >
            {description}
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
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
