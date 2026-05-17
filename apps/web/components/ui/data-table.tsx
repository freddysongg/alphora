"use client";

import type { ReactElement } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import type {
  ColumnDef,
  RowData,
  SortingState,
} from "@tanstack/react-table";
import { CaretDown, CaretUp, CaretUpDown } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/cn";

declare module "@tanstack/react-table" {
  interface ColumnMeta<TData extends RowData, TValue> {
    numeric?: boolean;
    align?: "left" | "right" | "center";
  }
}

export interface DataTableProps<TData> {
  data: TData[];
  columns: ColumnDef<TData, unknown>[];
  selectedRowId?: string;
  getRowId?: (row: TData, index: number) => string;
  onRowClick?: (row: TData) => void;
  emptyState?: ReactElement | string;
  initialSorting?: SortingState;
  className?: string;
}

const defaultEmptyState = "No rows yet.";

export function DataTable<TData>(props: DataTableProps<TData>): ReactElement {
  const {
    data,
    columns,
    selectedRowId,
    getRowId,
    onRowClick,
    emptyState = defaultEmptyState,
    initialSorting,
    className,
  } = props;

  const table = useReactTable<TData>({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId,
    state: initialSorting ? { sorting: initialSorting } : undefined,
  });

  const totalColumns = columns.length;

  return (
    <div className={cn("w-full overflow-x-auto", className)}>
      <table className="w-full border-collapse text-sm">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} className="border-b border-line">
              {headerGroup.headers.map((header) => {
                const meta = header.column.columnDef.meta;
                const isNumeric = meta?.numeric ?? false;
                const canSort = header.column.getCanSort();
                const sortDir = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    scope="col"
                    className={cn(
                      "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3",
                      isNumeric ? "text-right" : "text-left",
                      canSort && "cursor-pointer select-none hover:text-fg",
                    )}
                    onClick={
                      canSort
                        ? header.column.getToggleSortingHandler()
                        : undefined
                    }
                  >
                    <span
                      className={cn(
                        "inline-flex items-center gap-1",
                        isNumeric && "flex-row-reverse",
                      )}
                    >
                      {flexRender(
                        header.column.columnDef.header,
                        header.getContext(),
                      )}
                      {canSort ? (
                        sortDir === "asc" ? (
                          <CaretUp size={10} weight="regular" />
                        ) : sortDir === "desc" ? (
                          <CaretDown size={10} weight="regular" />
                        ) : (
                          <CaretUpDown size={10} weight="regular" />
                        )
                      ) : null}
                    </span>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.length === 0 ? (
            <tr>
              <td
                colSpan={totalColumns}
                className="h-20 text-center text-fg-subtle text-sm"
              >
                {emptyState}
              </td>
            </tr>
          ) : (
            table.getRowModel().rows.map((row) => {
              const isSelected = selectedRowId === row.id;
              return (
                <tr
                  key={row.id}
                  data-state={isSelected ? "selected" : undefined}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  className={cn(
                    "h-10 border-b border-line/60 transition-colors duration-150 hover:bg-surface-2",
                    onRowClick && "cursor-pointer",
                    isSelected && "bg-surface-2 border-l-2 border-l-accent",
                  )}
                >
                  {row.getVisibleCells().map((cell) => {
                    const meta = cell.column.columnDef.meta;
                    const isNumeric = meta?.numeric ?? false;
                    return (
                      <td
                        key={cell.id}
                        className={cn(
                          "px-3 text-fg",
                          isNumeric
                            ? "text-right font-mono tabular-nums"
                            : "text-left",
                        )}
                      >
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
