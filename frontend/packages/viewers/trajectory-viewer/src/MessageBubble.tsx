import { Suspense, lazy, useId, useState, type CSSProperties, type ReactNode } from "react";

import type { TrajectoryMessage } from "./types";

interface MessageBubbleProps {
  message: TrajectoryMessage;
  renderContent?: (msg: TrajectoryMessage) => ReactNode;
  renderCollapsedContent?: (msg: TrajectoryMessage) => ReactNode;
  renderToolCalls?: (msg: TrajectoryMessage) => ReactNode;
  actions?: ReactNode;
  showMetaLine?: boolean;
  metaFields?: string[];
  className?: string;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  collapsedContentHeight?: number;
  expandLabel?: string;
  collapseLabel?: string;
}

const DEFAULT_META_FIELDS = ["created_at", "latency", "latency_ms", "duration_ms"];
const DEFAULT_COLLAPSED_CONTENT_HEIGHT = 280;
const DEFAULT_EXPAND_LABEL = "Expand";
const DEFAULT_COLLAPSE_LABEL = "Collapse";
const PREVIEW_CHAR_LIMIT = 1_200;
const PREVIEW_MAX_DEPTH = 8;
const PREVIEW_STRING_CHUNK_SIZE = 128;
const MarkdownRenderer = lazy(async () => {
  const module = await import("@agentlens/markdown-renderer");
  return { default: module.MarkdownRenderer };
});
const JsonRenderer = lazy(async () => {
  const module = await import("@agentlens/json-renderer");
  return { default: module.JsonRenderer };
});

export function MessageBubble({
  message,
  renderContent,
  renderCollapsedContent,
  renderToolCalls,
  actions,
  showMetaLine = false,
  metaFields = DEFAULT_META_FIELDS,
  className,
  collapsible = false,
  defaultCollapsed = false,
  collapsedContentHeight = DEFAULT_COLLAPSED_CONTENT_HEIGHT,
  expandLabel = DEFAULT_EXPAND_LABEL,
  collapseLabel = DEFAULT_COLLAPSE_LABEL,
}: MessageBubbleProps) {
  const roleKind = getRoleKind(message.role);
  const metaItems = showMetaLine ? getMetaItems(message, metaFields) : [];
  const hasToolCalls = message.tool_calls !== undefined && message.tool_calls !== null;
  const contentId = useId();
  const [expanded, setExpanded] = useState(!defaultCollapsed);
  const renderRichBody = !collapsible || expanded;
  const bodyStyle = {
    "--trajectory-collapsed-content-height": `${collapsedContentHeight}px`,
  } as CSSProperties;

  return (
    <article
      className={joinClassNames(
        "agentlens-trajectory-message",
        `agentlens-trajectory-message--${roleKind}`,
        className,
      )}
    >
      <div className="agentlens-trajectory-bubble">
        <header className="agentlens-trajectory-message-header">
          <div className="agentlens-trajectory-message-header-main">
            <span className="agentlens-trajectory-role-label">{getRoleLabel(message.role)}</span>
            {metaItems.length > 0 ? (
              <span className="agentlens-trajectory-meta-line">{metaItems.join(" · ")}</span>
            ) : null}
          </div>
          {actions !== undefined || collapsible ? (
            <div className="agentlens-trajectory-message-header-actions">
              {actions}
              {collapsible ? (
                <button
                  type="button"
                  className="agentlens-trajectory-collapse-button"
                  aria-controls={contentId}
                  aria-expanded={expanded}
                  aria-label={expanded ? collapseLabel : expandLabel}
                  onClick={() => setExpanded((current) => !current)}
                >
                  {expanded ? collapseLabel : expandLabel}
                </button>
              ) : null}
            </div>
          ) : null}
        </header>
        <div
          id={contentId}
          role="region"
          className={joinClassNames(
            "agentlens-trajectory-bubble-body",
            collapsible && !expanded && "agentlens-trajectory-bubble-body--collapsed",
          )}
          style={bodyStyle}
        >
          <div className="agentlens-trajectory-content">
            {renderRichBody ? (
              renderContent ? renderContent(message) : renderDefaultContent(message.content)
            ) : renderCollapsedContent ? (
              renderCollapsedContent(message)
            ) : renderContent ? (
              renderContent(message)
            ) : (
              <ContentPreview value={message.content} />
            )}
          </div>
          {renderRichBody && hasToolCalls ? (
            <details className="agentlens-trajectory-tool-calls">
              <summary>Tool calls</summary>
              <div className="agentlens-trajectory-tool-calls-body">
                {renderToolCalls ? renderToolCalls(message) : renderDefaultToolCalls(message)}
              </div>
            </details>
          ) : null}
        </div>
      </div>
    </article>
  );
}

function renderDefaultContent(content: unknown) {
  if (typeof content === "string") {
    return (
      <Suspense fallback={<TextFallback value={content} />}>
        <MarkdownRenderer content={content} />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<TextFallback value={content} />}>
      <JsonRenderer value={content} collapsed={false} />
    </Suspense>
  );
}

function renderDefaultToolCalls(message: TrajectoryMessage) {
  return (
    <Suspense fallback={<TextFallback value={message.tool_calls} />}>
      <JsonRenderer value={message.tool_calls} collapsed={false} />
    </Suspense>
  );
}

function TextFallback({ value }: { value: unknown }) {
  return <ContentPreview value={value} loading />;
}

function ContentPreview({ value, loading = false }: { value: unknown; loading?: boolean }) {
  return (
    <pre
      className="agentlens-trajectory-content-preview"
      data-render-state={loading ? "loading" : "collapsed"}
    >
      {formatPreviewValue(value)}
    </pre>
  );
}

function formatPreviewValue(value: unknown): string {
  let preview = "";
  for (const token of iteratePreviewTokens(value, new WeakSet<object>(), 0)) {
    const remaining = PREVIEW_CHAR_LIMIT - preview.length;
    if (token.length > remaining) {
      return `${preview}${token.slice(0, remaining).trimEnd()}\u2026`;
    }
    preview += token;
  }
  return preview;
}

function* iteratePreviewTokens(
  value: unknown,
  seen: WeakSet<object>,
  depth: number,
): Generator<string> {
  if (typeof value === "string") {
    if (depth === 0) {
      yield value;
    } else {
      yield* iterateQuotedStringTokens(value);
    }
    return;
  }
  if (value === null || typeof value !== "object") {
    yield String(value);
    return;
  }
  if (seen.has(value)) {
    yield '"[Circular]"';
    return;
  }
  if (depth >= PREVIEW_MAX_DEPTH) {
    yield '"[Max depth]"';
    return;
  }

  seen.add(value);
  try {
    if (Array.isArray(value)) {
      yield "[";
      for (let index = 0; index < value.length; index += 1) {
        if (index > 0) {
          yield ", ";
        }
        yield* iteratePreviewTokens(value[index], seen, depth + 1);
      }
      yield "]";
      return;
    }

    yield "{";
    let hasPreviousEntry = false;
    const record = value as Record<string, unknown>;
    for (const key in record) {
      if (!Object.prototype.hasOwnProperty.call(record, key)) {
        continue;
      }
      if (hasPreviousEntry) {
        yield ", ";
      }
      hasPreviousEntry = true;
      yield* iterateQuotedStringTokens(key);
      yield ": ";
      yield* iteratePreviewTokens(record[key], seen, depth + 1);
    }
    yield "}";
  } finally {
    seen.delete(value);
  }
}

function* iterateQuotedStringTokens(value: string): Generator<string> {
  yield '"';
  let chunk = "";
  for (let index = 0; index < value.length; index += 1) {
    chunk += escapeJsonCharacter(value[index] ?? "");
    if (chunk.length >= PREVIEW_STRING_CHUNK_SIZE) {
      yield chunk;
      chunk = "";
    }
  }
  if (chunk.length > 0) {
    yield chunk;
  }
  yield '"';
}

function escapeJsonCharacter(character: string): string {
  if (character === '"') {
    return '\\"';
  }
  if (character === "\\") {
    return "\\\\";
  }
  if (character === "\b") {
    return "\\b";
  }
  if (character === "\f") {
    return "\\f";
  }
  if (character === "\n") {
    return "\\n";
  }
  if (character === "\r") {
    return "\\r";
  }
  if (character === "\t") {
    return "\\t";
  }
  const code = character.charCodeAt(0);
  return code < 0x20 ? `\\u${code.toString(16).padStart(4, "0")}` : character;
}

function getRoleKind(role: string): "system" | "user" | "assistant" | "tool" | "unknown" | "other" {
  const normalized = role.trim().toLowerCase();
  if (
    normalized === "system" ||
    normalized === "user" ||
    normalized === "assistant" ||
    normalized === "tool"
  ) {
    return normalized;
  }
  if (normalized === "unknown" || normalized === "") {
    return "unknown";
  }
  return "other";
}

function getRoleLabel(role: string): string {
  const normalized = role.trim();
  if (normalized.toLowerCase() === "tool") {
    return "Tool";
  }
  return normalized === "" ? "unknown" : normalized;
}

function getMetaItems(message: TrajectoryMessage, fields: string[]): string[] {
  return fields.flatMap((field) => {
    const value = message.raw[field];
    if (value === undefined || value === null || value === "") {
      return [];
    }
    return [`${field}: ${formatMetaValue(field, value)}`];
  });
}

function formatMetaValue(field: string, value: unknown): string {
  if (typeof value === "string" && isTimestampMetaField(field)) {
    return formatTimestampMeta(value);
  }

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function isTimestampMetaField(field: string): boolean {
  return /_at$/i.test(field);
}

function formatTimestampMeta(value: string): string {
  const normalized = normalizeIsoTimestamp(value);
  const timestamp = Date.parse(normalized);
  if (Number.isNaN(timestamp)) {
    return value;
  }

  const date = new Date(timestamp);
  return [
    pad(date.getUTCFullYear(), 4),
    pad(date.getUTCMonth() + 1, 2),
    pad(date.getUTCDate(), 2),
  ].join("-") + ` ${[
    pad(date.getUTCHours(), 2),
    pad(date.getUTCMinutes(), 2),
    pad(date.getUTCSeconds(), 2),
  ].join(":")}`;
}

function normalizeIsoTimestamp(value: string): string {
  const trimmed = value.trim();
  if (trimmed === "") {
    return value;
  }

  const normalized = trimmed.replace(/\s+/, "T");
  if (hasExplicitTimeZone(normalized)) {
    return normalized;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    return `${normalized}T00:00:00Z`;
  }
  return `${normalized}Z`;
}

function hasExplicitTimeZone(value: string): boolean {
  return /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
}

function pad(value: number, length: number): string {
  return String(value).padStart(length, "0");
}

function joinClassNames(...names: Array<string | undefined | false>): string {
  return names.filter(Boolean).join(" ");
}
