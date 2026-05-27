import { Suspense, lazy, memo, useState } from "react";
import { Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { CellPresentation } from "@/features/row-view/cells/cellUtils";
import {
  copyText,
  getLineClampStyle,
  toCellText,
  truncateMultilinePreview,
  truncatePreview,
} from "@/features/row-view/cells/cellUtils";

interface MarkdownCellProps {
  value: unknown;
  presentation?: CellPresentation;
  previewLines?: number;
  richPreview?: boolean;
}

const MarkdownRenderer = lazy(async () => {
  const module = await import("@agentlens/markdown-renderer");
  return { default: module.MarkdownRenderer };
});

function MarkdownCellComponent({
  value,
  presentation = "table",
  previewLines = 1,
  richPreview = false,
}: MarkdownCellProps) {
  const [open, setOpen] = useState(false);
  const content = toCellText(value);

  if (value == null) {
    return <span className="text-muted-foreground">NULL</span>;
  }

  if (presentation === "detail") {
    return (
      <Suspense fallback={<RendererFallback content={content} className="p-3" />}>
        <MarkdownRenderer
          content={content}
          className="rounded-md border bg-background p-3 text-sm"
        />
      </Suspense>
    );
  }

  const preview =
    previewLines === 1 && !richPreview
      ? truncatePreview(content)
      : truncateMultilinePreview(content, richPreview ? 1200 : 800);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          className="block w-full min-w-0 text-left text-foreground hover:underline"
          style={getLineClampStyle(previewLines)}
          onClick={(event) => event.stopPropagation()}
        >
          {preview}
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-6xl">
        <DialogHeader className="pr-10">
          <DialogTitle>Markdown</DialogTitle>
          <DialogDescription className="sr-only">完整 Markdown 内容。</DialogDescription>
        </DialogHeader>
        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => copyText(content)}
          >
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            复制
          </Button>
        </div>
        {open ? (
          <Suspense fallback={<RendererFallback content={content} className="p-4" />}>
            <MarkdownRenderer
              content={content}
              className="rounded-md border bg-background p-4 text-sm"
              maxHeight={640}
            />
          </Suspense>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function RendererFallback({
  content,
  className,
}: {
  content: string;
  className: string;
}) {
  return (
    <pre className={`overflow-auto whitespace-pre-wrap break-words rounded-md border bg-background text-sm ${className}`}>
      {content}
    </pre>
  );
}

export const MarkdownCell = memo(
  MarkdownCellComponent,
  (prev, next) =>
    Object.is(prev.value, next.value) &&
    prev.presentation === next.presentation &&
    prev.previewLines === next.previewLines &&
    prev.richPreview === next.richPreview,
);
