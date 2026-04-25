import { JsonRenderer } from "@agentlens/json-renderer";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  getLineClampStyle,
  type CellPresentation,
} from "@/features/row-view/cells/cellUtils";
import { TextCell } from "@/features/row-view/cells/TextCell";

const JSON_PREVIEW_MAX_CHARS_PER_LINE = 160;
const JSON_PREVIEW_MAX_DEPTH = 2;
const JSON_PREVIEW_MAX_ITEMS = 3;

interface JsonCellProps {
  value: unknown;
  collapsed?: boolean;
  presentation?: CellPresentation;
  previewLines?: number;
  richPreview?: boolean;
}

type ParsedJson =
  | { ok: true; value: unknown }
  | { ok: false };

export function JsonCell({
  value,
  presentation = "table",
  previewLines = 1,
  richPreview = false,
}: JsonCellProps) {
  const parsed = parseJsonValue(value);

  if (!parsed.ok) {
    return <TextCell value={value} />;
  }

  if (value == null) {
    return <span className="text-muted-foreground">NULL</span>;
  }

  if (presentation === "detail") {
    return <JsonRenderer value={parsed.value} collapsed={false} maxDepth={10} />;
  }

  if (richPreview) {
    return (
      <div data-row-click-stop className="h-full min-w-0 overflow-auto rounded-md">
        <JsonRenderer value={parsed.value} collapsed={false} maxDepth={3} />
      </div>
    );
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className="block w-full min-w-0 text-left font-mono text-xs text-foreground hover:underline"
          style={getLineClampStyle(previewLines)}
          onClick={(event) => event.stopPropagation()}
        >
          {getJsonPreview(parsed.value, previewLines)}
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-6xl">
        <DialogHeader className="pr-10">
          <DialogTitle>JSON</DialogTitle>
          <DialogDescription className="sr-only">完整 JSON 树。</DialogDescription>
        </DialogHeader>
        <div className="max-h-[72vh] min-h-0 overflow-auto rounded-md">
          <JsonRenderer value={parsed.value} collapsed={false} maxDepth={10} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

function parseJsonValue(value: unknown): ParsedJson {
  if (value == null) {
    return { ok: true, value };
  }

  if (typeof value === "string") {
    try {
      return { ok: true, value: JSON.parse(value) as unknown };
    } catch {
      return { ok: false };
    }
  }

  if (typeof value === "object") {
    return { ok: true, value };
  }

  return { ok: true, value };
}

function getJsonPreview(value: unknown, previewLines: number): string {
  return truncatePreview(
    formatPreviewValue(value, 0),
    JSON_PREVIEW_MAX_CHARS_PER_LINE * previewLines,
  );
}

function formatPreviewValue(value: unknown, depth: number): string {
  if (Array.isArray(value)) {
    return formatArrayPreview(value, depth);
  }

  if (typeof value === "object" && value !== null) {
    return formatObjectPreview(value as Record<string, unknown>, depth);
  }

  if (typeof value === "string") {
    return `"${truncatePreview(value.replace(/\s+/g, " "), 48)}"`;
  }

  if (value === null) {
    return "null";
  }

  return String(value);
}

function formatObjectPreview(value: Record<string, unknown>, depth: number): string {
  const entries = Object.entries(value);
  if (entries.length === 0) {
    return "{}";
  }

  if (depth >= JSON_PREVIEW_MAX_DEPTH) {
    return `{${entries.length} keys}`;
  }

  const visibleEntries = entries.slice(0, JSON_PREVIEW_MAX_ITEMS);
  const body = visibleEntries
    .map(([key, entryValue]) => `${key}: ${formatPreviewValue(entryValue, depth + 1)}`)
    .join(", ");
  const suffix = entries.length > visibleEntries.length ? ", ..." : "";

  return `{${body}${suffix}}`;
}

function formatArrayPreview(value: unknown[], depth: number): string {
  if (value.length === 0) {
    return "[]";
  }

  if (depth >= JSON_PREVIEW_MAX_DEPTH) {
    return `[${value.length} items]`;
  }

  const visibleItems = value.slice(0, JSON_PREVIEW_MAX_ITEMS);
  const body = visibleItems
    .map((item) => formatPreviewValue(item, depth + 1))
    .join(", ");
  const suffix = value.length > visibleItems.length ? ", ..." : "";

  return `[${body}${suffix}]`;
}

function truncatePreview(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength)}...`;
}
