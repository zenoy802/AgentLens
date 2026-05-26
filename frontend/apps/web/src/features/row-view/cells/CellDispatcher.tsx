import { memo } from "react";

import type { FieldRender } from "@/api/types";
import type { CellPresentation } from "@/features/row-view/cells/cellUtils";
import { CodeCell } from "@/features/row-view/cells/CodeCell";
import { JsonCell } from "@/features/row-view/cells/JsonCell";
import { MarkdownCell } from "@/features/row-view/cells/MarkdownCell";
import { RawCell } from "@/features/row-view/cells/RawCell";
import { TextCell } from "@/features/row-view/cells/TextCell";
import { TimestampCell } from "@/features/row-view/cells/TimestampCell";

interface CellDispatcherProps {
  value: unknown;
  render: FieldRender;
  presentation?: CellPresentation;
  previewLines?: number;
  richPreview?: boolean;
}

function CellDispatcherComponent({
  value,
  render,
  presentation = "table",
  previewLines = 1,
  richPreview = false,
}: CellDispatcherProps) {
  switch (render.type) {
    case "markdown":
      return (
        <MarkdownCell
          value={value}
          presentation={presentation}
          previewLines={previewLines}
          richPreview={richPreview}
        />
      );
    case "json":
      return (
        <JsonCell
          value={value}
          collapsed={render.collapsed ?? true}
          presentation={presentation}
          previewLines={previewLines}
          richPreview={richPreview}
        />
      );
    case "code":
      return (
        <CodeCell
          value={value}
          language={render.language ?? "plain"}
          presentation={presentation}
          previewLines={previewLines}
          richPreview={richPreview}
        />
      );
    case "timestamp":
      return <TimestampCell value={value} format={render.format ?? "YYYY-MM-DD HH:mm:ss"} />;
    case "text":
    case "tag":
      return <TextCell value={value} previewLines={previewLines} />;
    default:
      if (typeof value === "object" && value !== null) {
        return <RawCell value={value} />;
      }
      return <TextCell value={value} previewLines={previewLines} />;
  }
}

export const CellDispatcher = memo(
  CellDispatcherComponent,
  (prev, next) =>
    Object.is(prev.value, next.value) &&
    fieldRenderEqual(prev.render, next.render) &&
    prev.presentation === next.presentation &&
    prev.previewLines === next.previewLines &&
    prev.richPreview === next.richPreview,
);

function fieldRenderEqual(left: FieldRender, right: FieldRender): boolean {
  return (
    left.type === right.type &&
    getRenderOption(left, "language") === getRenderOption(right, "language") &&
    getRenderOption(left, "format") === getRenderOption(right, "format") &&
    getRenderOption(left, "collapsed") === getRenderOption(right, "collapsed")
  );
}

function getRenderOption(
  render: FieldRender,
  key: "language" | "format" | "collapsed",
): string | boolean | undefined {
  const value = key in render ? render[key] : undefined;
  return typeof value === "string" || typeof value === "boolean" ? value : undefined;
}
