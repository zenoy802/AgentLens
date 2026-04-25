import {
  memo,
  useEffect,
  useMemo,
  useRef,
  type CSSProperties,
  type MouseEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { ArrowDown, ArrowUp, Columns3, Copy, Maximize2, Rows3 } from "lucide-react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type Row as TableRow,
  type Table,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";

import type { Column, FieldRender, Row } from "@/api/types";
import { FullscreenViewDialog } from "@/components/common/FullscreenViewDialog";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { CellDispatcher } from "@/features/row-view/cells/CellDispatcher";
import { cn } from "@/lib/utils";
import { stringifyRawValue } from "@/features/row-view/cells/RawCell";
import { ColumnHeaderMenu } from "@/features/row-view/ColumnHeaderMenu";
import { getStableRowIdentity } from "@/features/row-view/rowIdentity";
import {
  useQueryStore,
  type ColumnPinDirection,
  type RowHeightMode,
  type TableConfig,
} from "@/stores/queryStore";

interface RowTableProps {
  columns: Column[];
  rows: Row[];
  onRowClick?: (row: Row, rowNumber: number) => void;
  isFullscreen?: boolean;
}

const ROW_NUMBER_COLUMN_WIDTH = 56;
const DEFAULT_DATA_COLUMN_WIDTH = 200;
const ROW_NUMBER_COLUMN_ID = "__agentlens_internal_row_number";
const DATA_COLUMN_ID_PREFIX = "__agentlens_internal_data_column_";

const ROW_HEIGHT_OPTIONS: Array<{
  mode: RowHeightMode;
  label: string;
  height: number;
  previewLines: number;
}> = [
  { mode: "compact", label: "单行", height: 36, previewLines: 1 },
  { mode: "medium", label: "2行", height: 64, previewLines: 2 },
  { mode: "large", label: "4行", height: 104, previewLines: 4 },
  { mode: "tall", label: "高预览", height: 160, previewLines: 6 },
];
const RICH_PREVIEW_ROW_HEIGHT = 220;

function RowTableComponent({ columns, rows, onRowClick, isFullscreen = false }: RowTableProps) {
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const fieldRenders = useQueryStore((state) => state.fieldRenders);
  const tableConfig = useQueryStore((state) => state.tableConfig);
  const visibleColumns = useMemo(
    () => columns.filter((column) => !tableConfig.hidden_columns.includes(column.name)),
    [columns, tableConfig.hidden_columns],
  );
  const sortedRows = useMemo(
    () => sortRows(rows, tableConfig.sort[0]),
    [rows, tableConfig.sort],
  );
  const rowHeightConfig = getRowHeightConfig(tableConfig.row_height, tableConfig.rich_preview);
  useEffect(() => {
    tableContainerRef.current?.scrollTo({ top: 0 });
  }, [rowHeightConfig.mode, tableConfig.rich_preview]);

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
      ...visibleColumns.map<ColumnDef<Row, unknown>>((column) => ({
        id: getDataColumnId(column.name),
        accessorFn: (row) => row[column.name],
        header: () => (
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <span className="min-w-0 truncate" title={column.name}>
              {column.name}
            </span>
            <ColumnSortIndicator columnName={column.name} />
            <ColumnHeaderMenu columnName={column.name} />
          </div>
        ),
        cell: (ctx) => {
          const value = ctx.getValue();
          const render = fieldRenders[column.name] ?? getDefaultRender(value);

          return (
            <CopyableCell value={value}>
              <CellDispatcher
                value={value}
                render={render}
                previewLines={rowHeightConfig.previewLines}
                richPreview={tableConfig.rich_preview}
              />
            </CopyableCell>
          );
        },
        size: DEFAULT_DATA_COLUMN_WIDTH,
        minSize: 60,
        enableResizing: true,
      })),
    ],
    [fieldRenders, rowHeightConfig.previewLines, tableConfig.rich_preview, visibleColumns],
  );

  const table = useReactTable({
    data: sortedRows,
    columns: columnDefs,
    getCoreRowModel: getCoreRowModel(),
    enableColumnResizing: true,
    columnResizeMode: "onEnd",
    getRowId: (row, index) => `${getStableRowIdentity(row, columns, index)}:${index}`,
  });

  const tableRows = table.getRowModel().rows;

  const resultSummary = `${rows.length} 行 / ${columns.length} 列`;

  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border bg-background shadow-sm",
        isFullscreen && "flex h-full min-h-0 flex-col",
      )}
    >
      <div className="flex min-h-10 items-center justify-between gap-2 border-b bg-muted/40 px-3 py-1.5">
        <div className="text-xs font-medium text-muted-foreground">
          {resultSummary}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <RowHeightControl value={rowHeightConfig.mode} />
          <RichPreviewToggle enabled={tableConfig.rich_preview} />
          <ColumnVisibilityMenu columns={columns} tableConfig={tableConfig} />
          {!isFullscreen ? (
            <FullscreenViewDialog
              title="查询结果"
              description={resultSummary}
              trigger={
                <button
                  type="button"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                  aria-label="全屏查看查询结果"
                  title="全屏"
                >
                  <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              }
            >
              <RowTable
                columns={columns}
                rows={rows}
                onRowClick={onRowClick}
                isFullscreen
              />
            </FullscreenViewDialog>
          ) : null}
        </div>
      </div>
      <div
        ref={tableContainerRef}
        data-row-table-container
        className={cn(
          "min-h-[260px] overflow-auto",
          isFullscreen ? "min-h-0 flex-1" : "h-[520px]",
        )}
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
                  const columnName = getDataColumnName(header.column.id);
                  const pinStyle =
                    columnName === null
                      ? undefined
                      : getPinnedColumnStyle({
                          columnName,
                          table,
                          visibleColumns,
                          tableConfig,
                          zIndex: 25,
                        });
                  return (
                    <th
                      key={header.id}
                      className={cn(
                        "relative flex h-9 items-center border-b border-r px-3 text-xs font-semibold text-muted-foreground",
                        isRowNumber && "sticky left-0 z-30 justify-center bg-muted px-2",
                        pinStyle !== undefined && "bg-muted shadow-sm",
                      )}
                      colSpan={header.colSpan}
                      style={{ ...getColumnStyle(header.getSize()), ...pinStyle }}
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
            key={`${rowHeightConfig.mode}:${tableConfig.rich_preview ? "rich" : "plain"}`}
            rows={tableRows}
            tableContainerRef={tableContainerRef}
            onRowClick={onRowClick}
            visibleColumns={visibleColumns}
            table={table}
            tableConfig={tableConfig}
            rowHeight={rowHeightConfig.height}
          />
        </table>
      </div>
    </div>
  );
}

function RowHeightControl({ value }: { value: RowHeightMode }) {
  const setRowHeight = useQueryStore((state) => state.setRowHeight);

  return (
    <div className="flex items-center rounded-md border bg-background p-0.5">
      <Rows3 className="mx-1 h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
      {ROW_HEIGHT_OPTIONS.map((option) => (
        <button
          key={option.mode}
          type="button"
          className={cn(
            "h-6 rounded px-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground",
            value === option.mode && "bg-accent text-foreground",
          )}
          aria-pressed={value === option.mode}
          title={`行高：${option.label}`}
          onClick={() => setRowHeight(option.mode)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function RichPreviewToggle({ enabled }: { enabled: boolean }) {
  const setRichPreview = useQueryStore((state) => state.setRichPreview);

  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-7 items-center rounded-md border bg-background px-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground",
        enabled && "border-primary text-foreground shadow-sm",
      )}
      aria-pressed={enabled}
      title="富预览：在 Markdown / JSON / Code 单元格内直接渲染内容"
      onClick={() => setRichPreview(!enabled)}
    >
      富预览
    </button>
  );
}

function ColumnVisibilityMenu({
  columns,
  tableConfig,
}: {
  columns: Column[];
  tableConfig: TableConfig;
}) {
  const toggleHiddenColumn = useQueryStore((state) => state.toggleHiddenColumn);
  const hiddenColumns = new Set(tableConfig.hidden_columns);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="配置列可见性"
          title="列可见性"
        >
          <Columns3 className="h-3.5 w-3.5" aria-hidden="true" />
          列
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-80 w-56 overflow-y-auto">
        <DropdownMenuLabel>列可见性</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {columns.map((column) => (
          <DropdownMenuCheckboxItem
            key={column.name}
            checked={!hiddenColumns.has(column.name)}
            onCheckedChange={() => toggleHiddenColumn(column.name)}
          >
            <span className="truncate" title={column.name}>
              {column.name}
            </span>
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

type VirtualizedTableBodyProps = {
  rows: Array<TableRow<Row>>;
  tableContainerRef: RefObject<HTMLDivElement>;
  onRowClick?: (row: Row, rowNumber: number) => void;
  visibleColumns: Column[];
  table: Table<Row>;
  tableConfig: TableConfig;
  rowHeight: number;
};

function VirtualizedTableBody({
  rows,
  tableContainerRef,
  onRowClick,
  visibleColumns,
  table,
  tableConfig,
  rowHeight,
}: VirtualizedTableBodyProps) {
  const rowVirtualizer = useVirtualizer<HTMLDivElement, HTMLTableRowElement>({
    count: rows.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => rowHeight,
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
              height: rowHeight,
              transform: `translateY(${virtualRow.start}px)`,
            }}
            onClick={(event) => {
              if (shouldIgnoreRowClick(event)) {
                return;
              }
              onRowClick?.(row.original, row.index + 1);
            }}
          >
            {row.getVisibleCells().map((cell) => {
              const isRowNumber = cell.column.id === ROW_NUMBER_COLUMN_ID;
              const columnName = getDataColumnName(cell.column.id);
              const pinStyle =
                columnName === null
                  ? undefined
                  : getPinnedColumnStyle({
                      columnName,
                      table,
                      visibleColumns,
                      tableConfig,
                      zIndex: 10,
                    });
              return (
                <td
                  key={cell.id}
                  className={cn(
                    "flex min-w-0 border-r px-3",
                    isRowNumber &&
                      "sticky left-0 z-[5] items-center justify-center bg-background px-2 text-xs text-muted-foreground group-hover:bg-accent/40",
                    !isRowNumber && "items-start py-2",
                    pinStyle !== undefined && "bg-background shadow-sm group-hover:bg-accent/40",
                  )}
                  style={{ ...getColumnStyle(cell.column.getSize()), height: rowHeight, ...pinStyle }}
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

function getRowHeightConfig(mode: RowHeightMode, richPreview: boolean) {
  const config = ROW_HEIGHT_OPTIONS.find((option) => option.mode === mode) ?? ROW_HEIGHT_OPTIONS[0];
  if (!richPreview) {
    return config;
  }

  return {
    ...config,
    height: RICH_PREVIEW_ROW_HEIGHT,
    previewLines: 8,
  };
}

function shouldIgnoreRowClick(event: MouseEvent<HTMLElement>): boolean {
  const target = event.target;
  if (!(target instanceof Element)) {
    return false;
  }

  return (
    target.closest(
      "button,a,input,select,textarea,[role='button'],[data-row-click-stop]",
    ) !== null
  );
}

function ColumnSortIndicator({ columnName }: { columnName: string }) {
  const direction =
    useQueryStore((state) => state.tableConfig.sort.find((item) => item.column === columnName)?.direction) ??
    null;

  if (direction === "asc") {
    return <ArrowUp className="h-3.5 w-3.5 shrink-0 text-foreground" aria-hidden="true" />;
  }

  if (direction === "desc") {
    return <ArrowDown className="h-3.5 w-3.5 shrink-0 text-foreground" aria-hidden="true" />;
  }

  return null;
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
          className="group/cell relative flex h-full min-w-0 flex-1 items-start pr-7"
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
          <div className="h-full min-w-0 flex-1">{children}</div>
          <button
            type="button"
            className="absolute right-1 top-1 hidden h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground group-hover/cell:flex"
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

function getColumnStyle(width: number): CSSProperties {
  return {
    width,
    minWidth: width,
    maxWidth: width,
  };
}

function getDefaultRender(value: unknown): FieldRender {
  return typeof value === "object" && value !== null ? { type: "json", collapsed: true } : { type: "text" };
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

function getDataColumnId(columnName: string): string {
  return `${DATA_COLUMN_ID_PREFIX}${columnName}`;
}

function getDataColumnName(columnId: string): string | null {
  if (!columnId.startsWith(DATA_COLUMN_ID_PREFIX)) {
    return null;
  }

  return columnId.slice(DATA_COLUMN_ID_PREFIX.length);
}

function getPinnedColumnStyle({
  columnName,
  table,
  visibleColumns,
  tableConfig,
  zIndex,
}: {
  columnName: string;
  table: Table<Row>;
  visibleColumns: Column[];
  tableConfig: TableConfig;
  zIndex: number;
}): CSSProperties | undefined {
  const pinDirection = getPinDirection(tableConfig, columnName);
  if (pinDirection === null) {
    return undefined;
  }

  const offset = getPinnedColumnOffset({
    columnName,
    pinDirection,
    table,
    visibleColumns,
    tableConfig,
  });

  if (pinDirection === "left") {
    return { left: offset, position: "sticky", zIndex };
  }

  return { position: "sticky", right: offset, zIndex };
}

function getPinnedColumnOffset({
  columnName,
  pinDirection,
  table,
  visibleColumns,
  tableConfig,
}: {
  columnName: string;
  pinDirection: ColumnPinDirection;
  table: Table<Row>;
  visibleColumns: Column[];
  tableConfig: TableConfig;
}): number {
  let offset = pinDirection === "left" ? ROW_NUMBER_COLUMN_WIDTH : 0;

  for (const column of visibleColumns) {
    if (column.name === columnName) {
      break;
    }

    if (pinDirection === "left" && getPinDirection(tableConfig, column.name) === "left") {
      offset += getTableColumnSize(table, column.name);
    }
  }

  if (pinDirection === "right") {
    for (const column of [...visibleColumns].reverse()) {
      if (column.name === columnName) {
        break;
      }

      if (getPinDirection(tableConfig, column.name) === "right") {
        offset += getTableColumnSize(table, column.name);
      }
    }
  }

  return offset;
}

function getTableColumnSize(table: Table<Row>, columnName: string): number {
  return table.getColumn(getDataColumnId(columnName))?.getSize() ?? DEFAULT_DATA_COLUMN_WIDTH;
}

function getPinDirection(tableConfig: TableConfig, columnName: string): ColumnPinDirection | null {
  const pinnedDirection = tableConfig.pinned_columns[columnName];
  if (pinnedDirection !== undefined) {
    return pinnedDirection;
  }

  return tableConfig.frozen_columns.includes(columnName) ? "left" : null;
}

function sortRows(rows: Row[], sortConfig: TableConfig["sort"][number] | undefined): Row[] {
  if (sortConfig === undefined) {
    return rows;
  }

  const directionMultiplier = sortConfig.direction === "asc" ? 1 : -1;

  return rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      const compared = compareValues(left.row[sortConfig.column], right.row[sortConfig.column]);
      if (compared !== 0) {
        return compared * directionMultiplier;
      }
      return left.index - right.index;
    })
    .map((item) => item.row);
}

function compareValues(left: unknown, right: unknown): number {
  if (left == null && right == null) {
    return 0;
  }
  if (left == null) {
    return -1;
  }
  if (right == null) {
    return 1;
  }
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  if (typeof left === "boolean" && typeof right === "boolean") {
    return Number(left) - Number(right);
  }

  return toSortableString(left).localeCompare(toSortableString(right), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function toSortableString(value: unknown): string {
  if (typeof value === "object" && value !== null) {
    return stringifyRawValue(value);
  }

  try {
    return String(value);
  } catch {
    return "";
  }
}

export const RowTable = memo(RowTableComponent);
