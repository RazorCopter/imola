import { render, screen, within } from "@testing-library/react";
import type { ColumnDef } from "@tanstack/react-table";
import { describe, expect, it } from "vitest";

import { DataTable } from "@/components/DataTable";

interface RowData {
  code: string;
  description: string;
}

const columns: ColumnDef<RowData>[] = [
  { accessorKey: "code", header: "Code" },
  { accessorKey: "description", header: "Description" },
];

const rowData: RowData = {
  code: "PRJ-001",
  description: "A complete description that must remain readable",
};
const data = [rowData];

describe("DataTable", () => {
  it("usa per default il sizing nativo sui contenuti e conserva lo scroll orizzontale", () => {
    render(<DataTable data={data} columns={columns} emptyLabel="No rows" />);

    const region = screen.getByRole("region", { name: "Tabella dati" });
    const table = within(region).getByRole("table");
    const description = screen.getByText(rowData.description);

    expect(region).toHaveAttribute("data-sizing-policy", "content");
    expect(region).toHaveClass("overflow-auto");
    expect(table).toHaveClass("w-max", "min-w-full", "table-auto");
    expect(description.closest("td")).toHaveClass("whitespace-nowrap");
    expect(description.closest("td")).not.toHaveClass("truncate");
  });

  it("applica classi colonna generiche senza cambiare la policy delle altre colonne", () => {
    render(
      <DataTable
        data={data}
        columns={columns}
        emptyLabel="No rows"
        getColumnClasses={(columnId) =>
          columnId === "description"
            ? { header: "min-w-64", cell: "min-w-64 whitespace-normal" }
            : undefined
        }
      />,
    );

    expect(screen.getByRole("columnheader", { name: "Description" })).toHaveClass("min-w-64");
    expect(screen.getByText(rowData.description).closest("td")).toHaveClass(
      "min-w-64",
      "whitespace-normal",
    );
    expect(screen.getByText("PRJ-001").closest("td")).toHaveClass("whitespace-nowrap");
  });
});
