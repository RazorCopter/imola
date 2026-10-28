import { formatDays, type DaysValue as ApiDaysValue } from "@/lib/format";

interface DaysValueProps {
  value: ApiDaysValue;
  label?: string;
  suffix?: boolean;
  className?: string;
}

/** Presentazione soltanto: il valore contabile arriva già calcolato dall'API. */
export function DaysValue({ value, label, suffix = true, className }: DaysValueProps) {
  const formatted = formatDays(value, { suffix });
  const raw = value === null || value === undefined || value === "" ? undefined : String(value);

  return (
    <span
      className={className ?? "tabular-nums"}
      title={raw ? `${label ?? "Valore API"}: ${raw} gg` : undefined}
    >
      {formatted}
    </span>
  );
}
