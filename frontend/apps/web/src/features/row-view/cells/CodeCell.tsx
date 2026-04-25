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

export function CodeCell({
  value,
  language,
  maxHeight,
  showLineNumbers = false,
  presentation = "table",
  previewLines = 1,
  richPreview = false,
}: CodeCellProps) {
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

  if (richPreview) {
    return (
      <div data-row-click-stop className="h-full min-w-0 overflow-auto rounded-md">
        <CodeRenderer code={code} language={language} showLineNumbers={showLineNumbers} />
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
          {previewLines === 1 ? truncatePreview(code) : truncateMultilinePreview(code)}
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-6xl">
        <DialogHeader className="pr-10">
          <DialogTitle>Code</DialogTitle>
          <DialogDescription className="sr-only">完整代码内容。</DialogDescription>
        </DialogHeader>
        <CodeRenderer
          code={code}
          language={language}
          maxHeight={maxHeight ?? 640}
          showLineNumbers={showLineNumbers}
        />
      </DialogContent>
    </Dialog>
  );
}
