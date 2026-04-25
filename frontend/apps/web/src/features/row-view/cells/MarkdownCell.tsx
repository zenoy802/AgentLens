import { MarkdownRenderer } from "@agentlens/markdown-renderer";
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

export function MarkdownCell({
  value,
  presentation = "table",
  previewLines = 1,
  richPreview = false,
}: MarkdownCellProps) {
  const content = toCellText(value);

  if (value == null) {
    return <span className="text-muted-foreground">NULL</span>;
  }

  if (presentation === "detail") {
    return (
      <MarkdownRenderer
        content={content}
        className="rounded-md border bg-background p-3 text-sm"
      />
    );
  }

  if (richPreview) {
    return (
      <div
        data-row-click-stop
        className="h-full min-w-0 overflow-auto rounded border bg-background p-2 text-xs"
      >
        <MarkdownRenderer content={content} />
      </div>
    );
  }

  const preview =
    previewLines === 1 ? truncatePreview(content) : truncateMultilinePreview(content);

  return (
    <Dialog>
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
        <MarkdownRenderer
          content={content}
          className="rounded-md border bg-background p-4 text-sm"
          maxHeight={640}
        />
      </DialogContent>
    </Dialog>
  );
}
