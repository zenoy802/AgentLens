import { memo, useMemo, useRef, type CSSProperties, type ReactNode, type RefObject } from "react";
import { Copy } from "lucide-react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type Row as TableRow,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";

import type { Column, Row } from "@/api/types";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { cn } from "@/lib/utils";
import { RawCell, stringifyRawValue } from "@/features/row-view/cells/RawCell";
import { TextCell } from "@/features/row-view/cells/TextCell";
import { getStableRowIdentity } from "@/features/row-view/rowIdentity";

interface RowTableProps {
  columns: Column[];
  rows: Row[];
  onRowClick?: (row: Row) => void;
}

const ROW_HEIGHT = 36;
const ROW_NUMBER_COLUMN_ID = "__agentlens_internal_row_number";
const DATA_COLUMN_ID_PREFIX = "__agentlens_internal_data_column_";

function RowTableComponent({ columns, rows, onRowClick }: RowTableProps) {
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const columnDefs = useMemo<Array<ColumnDef<Row, unknown>>>(
    () => [
      {
        id: ROW_NUMBER_COLUMN_ID,
        header: "#",
        cell: ({ row }) => row.index + 1,
        size: 56,
        minSize: 56,
        enableResizing: false,
      },
      ...columns.map<ColumnDef<Row, unknown>>((column, columnIndex) => ({
        id: getDataColumnId(columnIndex),
        accessorFn: (row) => row[column.name],
        header: column.name,
        cell: (ctx) => (
          <CopyableCell value={ctx.getValue()}>
            <DefaultCell value={ctx.getValue()} />
          </CopyableCell>
        ),
        size: 200,
        minSize: 60,
        enableResizing: true,
      })),
    ],
    [columns],
  );

  const table = useReactTable({
    data: rows,
    columns: columnDefs,
    getCoreRowModel: getCoreRowModel(),
    enableColumnResizing: true,
    columnResizeMode: "onEnd",
    getRowId: (row, index) => `${getStableRowIdentity(row, columns, index)}:${index}`,
  });

  const tableRows = table.getRowModel().rows;

  return (
    <div className="overflow-hidden rounded-lg border bg-background shadow-sm">
      <div
        ref={tableContainerRef}
        data-row-table-container
        className="h-[520px] min-h-[260px] overflow-auto"
      >
        <table
          className="grid min-w-full border-collapse text-left text-sm"
          style={{ width: table.getTotalSize() }}
        >
          <thead className="sticky top-0 z-10 grid bg-muted shadow-sm">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="flex w-full">
                {headerGroup.headers.map((header) => {
                  const isRowNumber = header.column.id === ROW_NUMBER_COLUMN_ID;
                  return (
                    <th
                      key={header.id}
                      className={cn(
                        "relative flex h-9 items-center border-b border-r px-3 text-xs font-semibold text-muted-foreground",
                        isRowNumber && "sticky left-0 z-30 justify-center bg-muted px-2",
                      )}
                      colSpan={header.colSpan}
                      style={getColumnStyle(header.getSize())}
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getCanResize() ? (
                        <div
                          aria-hidden="true"
                          className={cn(
                            "absolute right-0 top-0 h-full w-1 cursor-col-resize touch-none select-none",
                            "hover:bg-primary/40",
                            header.column.getIsResizing() && "bg-primary/70",
                          )}
                          onDoubleClick={() => header.column.resetSize()}
                          onMouseDown={header.getResizeHandler()}
                          onTouchStart={header.getResizeHandler()}
                        />
                      ) : null}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <VirtualizedTableBody
            rows={tableRows}
            tableContainerRef={tableContainerRef}
            onRowClick={onRowClick}
          />
        </table>
      </div>
    </div>
  );
}

type VirtualizedTableBodyProps = {
  rows: Array<TableRow<Row>>;
  tableContainerRef: RefObject<HTMLDivElement>;
  onRowClick?: (row: Row) => void;
};

function VirtualizedTableBody({
  rows,
  tableContainerRef,
  onRowClick,
}: VirtualizedTableBodyProps) {
  const rowVirtualizer = useVirtualizer<HTMLDivElement, HTMLTableRowElement>({
    count: rows.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  return (
    <tbody
      className="grid"
      style={{
        height: `${rowVirtualizer.getTotalSize()}px`,
        position: "relative",
      }}
    >
      {rowVirtualizer.getVirtualItems().map((virtualRow) => {
        const row = rows[virtualRow.index];
        return (
          <tr
            key={row.id}
            className={cn(
              "group absolute flex w-full border-b bg-background text-sm transition-colors hover:bg-accent/40",
              onRowClick !== undefined && "cursor-pointer",
            )}
            style={{
              height: ROW_HEIGHT,
              transform: `translateY(${virtualRow.start}px)`,
            }}
            onClick={() => onRowClick?.(row.original)}
          >
            {row.getVisibleCells().map((cell) => {
              const isRowNumber = cell.column.id === ROW_NUMBER_COLUMN_ID;
              return (
                <td
                  key={cell.id}
                  className={cn(
                    "flex h-9 min-w-0 items-center border-r px-3",
                    isRowNumber &&
                      "sticky left-0 z-[5] justify-center bg-background px-2 text-xs text-muted-foreground group-hover:bg-accent/40",
                  )}
                  style={getColumnStyle(cell.column.getSize())}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              );
            })}
          </tr>
        );
      })}
    </tbody>
  );
}

function CopyableCell({ value, children }: { value: unknown; children: ReactNode }) {
  const text = toClipboardText(value);
  const suppressRowClickRef = useRef(false);

  function handleCopy() {
    if (typeof navigator === "undefined" || navigator.clipboard === undefined) {
      return;
    }

    void navigator.clipboard.writeText(text).catch(() => undefined);
  }

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <div
          className="group/cell relative flex min-w-0 flex-1 items-center pr-7"
          onClickCapture={(event) => {
            if (suppressRowClickRef.current || event.ctrlKey) {
              suppressRowClickRef.current = false;
              event.stopPropagation();
            }
          }}
          onContextMenu={(event) => {
            suppressRowClickRef.current = true;
            event.stopPropagation();
          }}
        >
          <div className="min-w-0 flex-1">{children}</div>
          <button
            type="button"
            className="absolute right-1 top-1/2 hidden h-6 w-6 -translate-y-1/2 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground group-hover/cell:flex"
            aria-label="复制单元格值"
            title="复制"
            onClick={(event) => {
              event.stopPropagation();
              handleCopy();
            }}
          >
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent className="min-w-28" onClick={(event) => event.stopPropagation()}>
        <ContextMenuItem
          onSelect={(event) => {
            event.stopPropagation();
            handleCopy();
          }}
        >
          复制
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}

function DefaultCell({ value }: { value: unknown }) {
  if (typeof value === "object" && value !== null) {
    return <RawCell value={value} />;
  }

  return <TextCell value={value} />;
}

function getColumnStyle(width: number): CSSProperties {
  return {
    width,
    minWidth: width,
    maxWidth: width,
  };
}

function toClipboardText(value: unknown): string {
  if (typeof value === "object" && value !== null) {
    return stringifyRawValue(value);
  }

  try {
    return String(value);
  } catch {
    return "[unserializable value]";
  }
}

function getDataColumnId(columnIndex: number): string {
  return `${DATA_COLUMN_ID_PREFIX}${columnIndex}`;
}

export const RowTable = memo(RowTableComponent);
