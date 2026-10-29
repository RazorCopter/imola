import { useTranslation } from "react-i18next";
import { useId } from "react";
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
    <div className="flex min-h-32 items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 p-4 text-sm text-muted-foreground">
      {t("dashboard.noChartData")}
    </div>
  );
}

function Legend({ data, unit, premium }: { data: ChartDatum[]; unit?: string; premium?: boolean }) {
  return (
    <ul className="space-y-2 text-sm" aria-label="Legend">
      {data.map((item) => (
        <li
          key={item.key}
          className={
            premium
              ? "flex items-center justify-between gap-3 rounded-xl border border-border/70 bg-muted/20 px-3 py-2.5"
              : "flex items-center justify-between gap-3"
          }
        >
          <span className="flex min-w-0 items-center gap-2">
            <span
              className={
                premium ? "h-2.5 w-2.5 shrink-0 rounded-full" : "h-3 w-3 shrink-0 rounded-sm"
              }
              style={{ backgroundColor: item.color }}
              aria-hidden="true"
            />
            <span className="break-words">{item.label}</span>
          </span>
          <span className="font-medium tabular-nums">
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
  premium = false,
  caption,
}: {
  title: string;
  data: ChartDatum[];
  unit?: "days";
  premium?: boolean;
  caption?: string;
}) {
  const chartId = useId().replaceAll(":", "");
  const total = data.reduce((sum, item) => sum + item.value, 0);
  const visible = data.filter((item) => item.value > 0);
  return (
    <article
      className={
        premium
          ? "rounded-2xl border border-border bg-card p-5 shadow-subtle sm:p-6"
          : "rounded-xl border border-border bg-card p-5 shadow-subtle"
      }
    >
      <h2 className="font-semibold tracking-tight">{title}</h2>
      {visible.length === 0 ? (
        <div className="mt-4">
          <EmptyChart />
        </div>
      ) : (
        <div className="mt-3 grid items-center gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(10rem,1fr)]">
          <div
            className={premium ? "relative h-52 min-w-0" : "h-44 min-w-0"}
            role="img"
            aria-label={title}
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                {premium && (
                  <defs>
                    {visible.map((item, index) => (
                      <linearGradient
                        id={`${chartId}-${index}`}
                        key={item.key}
                        x1="0"
                        y1="0"
                        x2="1"
                        y2="1"
                      >
                        <stop offset="0%" stopColor={item.color} />
                        <stop offset="100%" stopColor={item.color} stopOpacity={0.65} />
                      </linearGradient>
                    ))}
                  </defs>
                )}
                <Pie
                  data={visible}
                  dataKey="value"
                  nameKey="label"
                  innerRadius="62%"
                  outerRadius="82%"
                  paddingAngle={premium && visible.length > 1 ? 4 : 2}
                  cornerRadius={premium ? 5 : 0}
                  stroke="none"
                  isAnimationActive={false}
                >
                  {visible.map((item, index) => (
                    <Cell
                      key={item.key}
                      fill={premium ? `url(#${chartId}-${index})` : item.color}
                      aria-label={item.label}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#101d38",
                    border: "1px solid #334963",
                    borderRadius: "12px",
                    color: "#fff",
                    boxShadow: "0 16px 40px rgba(0,0,0,.25)",
                  }}
                  itemStyle={{ color: "#fff" }}
                  formatter={(value: number, name: string) => [
                    unit === "days" ? formatDays(String(value)) : value,
                    name,
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
            {premium && (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
              >
                <span className="text-3xl font-semibold tabular-nums tracking-tight">{total}</span>
                <span className="mt-1 text-[10px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">
                  Progetti
                </span>
              </div>
            )}
          </div>
          <Legend data={data} unit={unit} premium={premium} />
        </div>
      )}
      {caption && <p className="dash-caption mt-3">{caption}</p>}
    </article>
  );
}
