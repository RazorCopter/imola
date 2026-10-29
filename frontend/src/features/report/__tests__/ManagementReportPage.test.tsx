import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { ManagementReportPage } from "../ManagementReportPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));

it("distingue il monte non allocato dalla quota assegnata ancora da consumare", async () => {
  vi.mocked(api.get).mockResolvedValue({
    date: "2026-10-29",
    projects: [],
    wallet: [],
    activities: [],
    organico_monte: "100",
    domains: [
      { domain: "EA", count: 1, reserved: "40", consumed: "20", remaining: "20" },
      { domain: "SA", count: 1, reserved: "20", consumed: "10", remaining: "10" },
    ],
    economics: {
      kpi: { total_cost: "0", daily_person_cost: "0" },
      by_source: [],
      monthly_trend: [],
    },
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ManagementReportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const insights = (await screen.findByText("monte non ancora allocato")).closest<HTMLElement>(
    ".report-insights",
  )!;
  const metric = (label: string) => within(insights).getByText(label).parentElement;
  expect(metric("monte organico ancora disponibile")).toHaveTextContent("70,00 gg");
  expect(metric("monte non ancora allocato")).toHaveTextContent("40,00 gg");
  expect(metric("allocato e ancora da consumare")).toHaveTextContent("30,00 gg");
});
