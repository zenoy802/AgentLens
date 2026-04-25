import { JsonRenderer } from "@agentlens/json-renderer";
import { MarkdownRenderer } from "@agentlens/markdown-renderer";
import type { ReactNode } from "react";

import type { TrajectoryMessage } from "./types";

interface MessageBubbleProps {
  message: TrajectoryMessage;
  renderContent?: (msg: TrajectoryMessage) => ReactNode;
  renderToolCalls?: (msg: TrajectoryMessage) => ReactNode;
  showMetaLine?: boolean;
  metaFields?: string[];
  className?: string;
}

const DEFAULT_META_FIELDS = ["created_at", "latency", "latency_ms", "duration_ms"];

export function MessageBubble({
  message,
  renderContent,
  renderToolCalls,
  showMetaLine = false,
  metaFields = DEFAULT_META_FIELDS,
  className,
}: MessageBubbleProps) {
  const roleKind = getRoleKind(message.role);
  const metaItems = showMetaLine ? getMetaItems(message, metaFields) : [];
  const hasToolCalls = message.tool_calls !== undefined && message.tool_calls !== null;

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
          <span className="agentlens-trajectory-role-label">{getRoleLabel(message.role)}</span>
          {metaItems.length > 0 ? (
            <span className="agentlens-trajectory-meta-line">{metaItems.join(" · ")}</span>
          ) : null}
        </header>
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
    return [`${field}: ${formatMetaValue(value)}`];
  });
}

function formatMetaValue(value: unknown): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function joinClassNames(...names: Array<string | undefined | false>): string {
  return names.filter(Boolean).join(" ");
}
