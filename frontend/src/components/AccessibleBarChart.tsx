import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDays } from "@/lib/format";

// eslint-disable-next-line react-refresh/only-export-components
export const CHART_PALETTE = {
  blue: "#2563eb",
  green: "#15803d",
  amber: "#b45309",
  slate: "#64748b",
} as const;

interface Series {
  key: string;
  label: string;
  color: string;
}

interface TooltipEntry {
  name?: string;
  value?: number | string;
  color?: string;
  payload?: Record<string, unknown>;
}

function formatEuro(value: number | string) {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(
    Number(value),
  );
}

function formatValue(value: number | string, unit: "days" | "euro") {
  return unit === "euro" ? formatEuro(value) : formatDays(value);
}

export function ChartTooltip({
  active,
  label,
  payload,
  unit,
}: {
  active?: boolean;
  label?: string;
  payload?: TooltipEntry[];
  unit: "days" | "euro";
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      data-testid="chart-tooltip"
      className="max-w-sm rounded-lg border border-slate-600 p-3 text-sm shadow-2xl"
      style={{ backgroundColor: "#0f172a", color: "#f8fafc", opacity: 1 }}
    >
      {label && <p className="mb-2 break-words font-semibold text-white">{label}</p>}
      <ul className="space-y-1.5">
        {payload.map((entry) => (
          <li key={entry.name} className="flex items-center justify-between gap-4">
            <span className="flex min-w-0 items-center gap-2 text-slate-300">
              <span
                aria-hidden="true"
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: entry.color ?? CHART_PALETTE.blue }}
              />
              <span>{entry.name}</span>
            </span>
            <strong className="shrink-0 tabular-nums text-white">
              {formatValue(entry.value ?? 0, unit)}
            </strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AccessibleBarChart({
  data,
  xKey,
  series,
  unit,
  hideXAxis = false,
}: {
  data: object[];
  xKey: string;
  series: Series[];
  unit: "days" | "euro";
  hideXAxis?: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 12 }}>
        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey={xKey}
          hide={hideXAxis}
          stroke="hsl(var(--muted-foreground))"
          tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
        />
        <YAxis
          stroke="hsl(var(--muted-foreground))"
          tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
          tickFormatter={(value: unknown) => {
            const numericValue = typeof value === "number" ? value : Number(String(value));
            return unit === "euro"
              ? formatEuro(numericValue).replace(",00", "")
              : formatDays(numericValue);
          }}
          width={88}
        />
        <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: "transparent" }} />
        <Legend wrapperStyle={{ color: "hsl(var(--foreground))", fontSize: 12 }} />
        {series.map((item) => (
          <Bar
            key={item.key}
            dataKey={item.key}
            name={item.label}
            fill={item.color}
            radius={[7, 7, 0, 0]}
            isAnimationActive={false}
            activeBar={{ fill: item.color, fillOpacity: 0.78, stroke: "#f8fafc", strokeWidth: 1 }}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
