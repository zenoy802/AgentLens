import type { CSSProperties } from "react";

import { stringifyRawValue } from "@/features/row-view/cells/RawCell";

export type CellPresentation = "table" | "detail";

export function toCellText(value: unknown): string {
  if (value == null) {
    return "NULL";
  }

  if (typeof value === "object") {
    return stringifyRawValue(value);
  }

  try {
    return String(value);
  } catch {
    return "[unserializable value]";
  }
}

export function truncatePreview(value: string, maxLength = 80): string {
  const firstLine = value.split(/\r?\n/, 1)[0] ?? "";
  if (firstLine.length <= maxLength) {
    return firstLine;
  }

  return `${firstLine.slice(0, maxLength)}...`;
}

export function truncateMultilinePreview(value: string, maxLength = 800): string {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength)}...`;
}

export function copyText(text: string): void {
  if (typeof navigator === "undefined" || navigator.clipboard === undefined) {
    return;
  }

  void navigator.clipboard.writeText(text).catch(() => undefined);
}

export function getLineClampStyle(lines: number): CSSProperties {
  return {
    display: "-webkit-box",
    WebkitBoxOrient: "vertical",
    WebkitLineClamp: lines,
    overflow: "hidden",
    overflowWrap: "anywhere",
    whiteSpace: "pre-wrap",
  };
}
