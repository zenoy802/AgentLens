import { JsonRenderer } from "@agentlens/json-renderer";
import { MarkdownRenderer } from "@agentlens/markdown-renderer";
import { useId, useState, type CSSProperties, type ReactNode } from "react";

import type { TrajectoryMessage } from "./types";

interface MessageBubbleProps {
  message: TrajectoryMessage;
  renderContent?: (msg: TrajectoryMessage) => ReactNode;
  renderToolCalls?: (msg: TrajectoryMessage) => ReactNode;
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

export function MessageBubble({
  message,
  renderContent,
  renderToolCalls,
  showMetaLine = false,
  metaFields = DEFAULT_META_FIELDS,
  className,
  collapsible = true,
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
            {renderContent ? renderContent(message) : renderDefaultContent(message.content)}
          </div>
          {hasToolCalls ? (
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
    return <MarkdownRenderer content={content} />;
  }

  return <JsonRenderer value={content} collapsed={false} />;
}

function renderDefaultToolCalls(message: TrajectoryMessage) {
  return <JsonRenderer value={message.tool_calls} collapsed={false} />;
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
