import { memo, useState } from "react";
import { CodeRenderer } from "@agentlens/code-renderer";

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
  getLineClampStyle,
  toCellText,
  truncateMultilinePreview,
  truncatePreview,
} from "@/features/row-view/cells/cellUtils";

interface CodeCellProps {
  value: unknown;
  language: string;
  maxHeight?: number;
  showLineNumbers?: boolean;
  presentation?: CellPresentation;
  previewLines?: number;
  richPreview?: boolean;
}

function CodeCellComponent({
  value,
  language,
  maxHeight,
  showLineNumbers = false,
  presentation = "table",
  previewLines = 1,
  richPreview = false,
}: CodeCellProps) {
  const [open, setOpen] = useState(false);
  const code = toCellText(value);

  if (value == null) {
    return <span className="text-muted-foreground">NULL</span>;
  }

  if (presentation === "detail") {
    return (
      <CodeRenderer
        code={code}
        language={language}
        maxHeight={maxHeight}
        showLineNumbers={showLineNumbers}
      />
    );
  }

  const preview =
    previewLines === 1 && !richPreview
      ? truncatePreview(code)
      : truncateMultilinePreview(code, richPreview ? 1200 : 800);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          type="button"
          className="block w-full min-w-0 text-left font-mono text-xs text-foreground hover:underline"
          style={getLineClampStyle(previewLines)}
          onClick={(event) => event.stopPropagation()}
        >
          {preview}
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-6xl">
        <DialogHeader className="pr-10">
          <DialogTitle>Code</DialogTitle>
          <DialogDescription className="sr-only">完整代码内容。</DialogDescription>
        </DialogHeader>
        {open ? (
          <CodeRenderer
            code={code}
            language={language}
            maxHeight={maxHeight ?? 640}
            showLineNumbers={showLineNumbers}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

export const CodeCell = memo(
  CodeCellComponent,
  (prev, next) =>
    Object.is(prev.value, next.value) &&
    prev.language === next.language &&
    prev.maxHeight === next.maxHeight &&
    prev.showLineNumbers === next.showLineNumbers &&
    prev.presentation === next.presentation &&
    prev.previewLines === next.previewLines &&
    prev.richPreview === next.richPreview,
);
