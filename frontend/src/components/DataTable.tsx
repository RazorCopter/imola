import { useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";

import { cn } from "@/lib/utils";

export interface DataTableColumnClasses {
  header?: string;
  cell?: string;
}

interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  emptyLabel: string;
  rowHeight?: number;
  onRowClick?: (row: T) => void;
  getColumnClasses?: (columnId: string) => DataTableColumnClasses | undefined;
}

export function DataTable<T>({
  data,
  columns,
  emptyLabel,
  rowHeight = 44,
  onRowClick,
  getColumnClasses,
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const rows = table.getRowModel().rows;

  if (rows.length === 0)
    return (
      <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        {emptyLabel}
      </div>
    );

  return (
    <div
      className="max-h-[62vh] overflow-auto rounded-lg border border-border bg-card"
      role="region"
      aria-label="Tabella dati"
      tabIndex={0}
      data-sizing-policy="content"
    >
      <table className="w-max min-w-full table-auto border-separate border-spacing-0 text-sm">
        <thead className="sticky top-0 z-10 bg-muted">
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => {
                const columnClasses = getColumnClasses?.(header.column.id);
                return (
                  <th
                    key={header.id}
                    className={cn(
                      "whitespace-nowrap border-b border-border px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground",
                      columnClasses?.header,
                    )}
                  >
                    <button
                      type="button"
                      className={
                        header.column.getCanSort() ? "cursor-pointer select-none" : "cursor-default"
                      }
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() === "asc"
                        ? " ↑"
                        : header.column.getIsSorted() === "desc"
                          ? " ↓"
                          : ""}
                    </button>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={cn(
                "border-b border-border",
                onRowClick && "cursor-pointer hover:bg-muted/60",
              )}
              style={{ height: rowHeight }}
              onClick={() => onRowClick?.(row.original)}
            >
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  className={cn(
                    "whitespace-nowrap border-b border-border px-3 py-2 align-middle",
                    getColumnClasses?.(cell.column.id)?.cell,
                  )}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
