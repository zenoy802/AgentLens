import { Suspense, lazy, memo, useState } from "react";

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
  toCellText,
  truncateMultilinePreview,
  type CellPresentation,
} from "@/features/row-view/cells/cellUtils";
import { TextCell } from "@/features/row-view/cells/TextCell";

interface JsonCellProps {
  value: unknown;
  collapsed?: boolean;
  presentation?: CellPresentation;
  previewLines?: number;
  richPreview?: boolean;
}

const JsonRenderer = lazy(async () => {
  const module = await import("@agentlens/json-renderer");
  return { default: module.JsonRenderer };
});

type ParsedJson =
  | { ok: true; value: unknown }
  | { ok: false };

function JsonCellComponent({
  value,
  collapsed = true,
  presentation = "table",
  previewLines = 1,
  richPreview = false,
}: JsonCellProps) {
  const [open, setOpen] = useState(false);

  if (value == null) {
    return <span className="text-muted-foreground">NULL</span>;
  }

  if (presentation === "detail") {
    return (
      <Suspense fallback={<TextCell value={value} />}>
        <JsonDetail value={value} collapsed={false} maxDepth={10} />
      </Suspense>
    );
  }

  const previewText = richPreview
    ? truncateMultilinePreview(toCellText(value), 1200)
    : truncatePreview(toCellText(value), 160 * previewLines);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          className="block w-full min-w-0 text-left font-mono text-xs text-foreground hover:underline"
          style={getLineClampStyle(previewLines)}
          onClick={(event) => event.stopPropagation()}
        >
          {previewText}
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-6xl">
        <DialogHeader className="pr-10">
          <DialogTitle>JSON</DialogTitle>
          <DialogDescription className="sr-only">完整 JSON 树。</DialogDescription>
        </DialogHeader>
        <div className="max-h-[72vh] min-h-0 overflow-auto rounded-md">
          {open ? (
            <Suspense fallback={<TextCell value={value} />}>
              <JsonDetail value={value} collapsed={false} maxDepth={10} />
            </Suspense>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function JsonDetail({
  value,
  collapsed,
  maxDepth,
}: {
  value: unknown;
  collapsed: boolean;
  maxDepth: number;
}) {
  const parsed = parseJsonValue(value);
  if (!parsed.ok) {
    return <TextCell value={value} />;
  }
  return <JsonRenderer value={parsed.value} collapsed={collapsed} maxDepth={maxDepth} />;
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

function truncatePreview(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength)}...`;
}

export const JsonCell = memo(
  JsonCellComponent,
  (prev, next) =>
    Object.is(prev.value, next.value) &&
    prev.collapsed === next.collapsed &&
    prev.presentation === next.presentation &&
    prev.previewLines === next.previewLines &&
    prev.richPreview === next.richPreview,
);
