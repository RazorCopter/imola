import { useTranslation } from "react-i18next";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { formatDays } from "@/lib/format";

export interface ChartDatum {
  key: string;
  label: string;
  value: number;
  color: string;
}

function EmptyChart() {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-48 items-center justify-center rounded-md bg-muted/40 p-4 text-sm text-muted-foreground">
      {t("dashboard.noChartData")}
    </div>
  );
}

function Legend({ data, unit }: { data: ChartDatum[]; unit?: string }) {
  return (
    <ul className="space-y-2 text-sm" aria-label="Legend">
      {data.map((item) => (
        <li key={item.key} className="flex items-center justify-between gap-3">
          <span className="flex min-w-0 items-center gap-2">
            <span
              className="h-3 w-3 shrink-0 rounded-sm"
              style={{ backgroundColor: item.color }}
              aria-hidden="true"
            />
            <span className="truncate">{item.label}</span>
          </span>
          <span className="font-mono tabular-nums">
            {unit === "days" ? formatDays(String(item.value)) : item.value}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function DonutChart({
  title,
  data,
  unit,
}: {
  title: string;
  data: ChartDatum[];
  unit?: "days";
}) {
  const visible = data.filter((item) => item.value > 0);
  return (
    <article className="rounded-lg border border-border bg-card p-4 shadow-subtle">
      <h2 className="font-semibold">{title}</h2>
      {visible.length === 0 ? (
        <div className="mt-4">
          <EmptyChart />
        </div>
      ) : (
        <div className="mt-3 grid items-center gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(10rem,1fr)]">
          <div className="h-52 min-w-0" role="img" aria-label={title}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={visible}
                  dataKey="value"
                  nameKey="label"
                  innerRadius="48%"
                  outerRadius="78%"
                  paddingAngle={2}
                >
                  {visible.map((item) => (
                    <Cell key={item.key} fill={item.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number, name: string) => [
                    unit === "days" ? formatDays(String(value)) : value,
                    name,
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <Legend data={data} unit={unit} />
        </div>
      )}
    </article>
  );
}
