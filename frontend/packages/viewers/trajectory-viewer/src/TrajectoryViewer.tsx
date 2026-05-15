import { MessageBubble } from "./MessageBubble";
import type {
  MessageClassNameResolver,
  MessageCollapseResolver,
  TrajectoryMessage,
  TrajectoryViewerProps,
} from "./types";

import "./styles.css";

const DEFAULT_AUTO_COLLAPSE_CHAR_LIMIT = 900;

export function TrajectoryViewer({
  trajectory,
  renderContent,
  renderToolCalls,
  filterRoles,
  className,
  messageClassName,
  renderMessageActions,
  showHeader = true,
  showMetaLine = false,
  metaFields,
  collapsibleMessages = false,
  defaultMessageCollapsed,
  collapsedContentHeight,
  expandLabel,
  collapseLabel,
}: TrajectoryViewerProps) {
  const messages = filterMessagesByRole(trajectory.messages, filterRoles);

  return (
    <section className={joinClassNames("agentlens-trajectory-viewer", className)}>
      {showHeader ? (
        <header className="agentlens-trajectory-header">
          <div>
            <div className="agentlens-trajectory-eyebrow">Trajectory</div>
            <h2 className="agentlens-trajectory-title">{trajectory.group_key}</h2>
          </div>
          <div className="agentlens-trajectory-count">
            {messages.length === trajectory.message_count
              ? `${trajectory.message_count} messages`
              : `${messages.length} / ${trajectory.message_count} messages`}
          </div>
        </header>
      ) : null}
      <div className="agentlens-trajectory-stream">
        {messages.map(({ message, originalIndex }) => (
          <MessageBubble
            key={`${message.row_identity}:${originalIndex}`}
            message={message}
            renderContent={renderContent}
            renderToolCalls={renderToolCalls}
            actions={renderMessageActions?.(message, originalIndex)}
            showMetaLine={showMetaLine}
            metaFields={metaFields}
            collapsible={collapsibleMessages}
            defaultCollapsed={resolveDefaultCollapsed(message, defaultMessageCollapsed)}
            collapsedContentHeight={collapsedContentHeight}
            expandLabel={expandLabel}
            collapseLabel={collapseLabel}
            className={resolveMessageClassName(message, originalIndex, messageClassName)}
          />
        ))}
      </div>
    </section>
  );
}

function filterMessagesByRole(
  messages: TrajectoryMessage[],
  filterRoles: string[] | undefined,
): Array<{ message: TrajectoryMessage; originalIndex: number }> {
  const indexedMessages = messages.map((message, originalIndex) => ({
    message,
    originalIndex,
  }));

  if (filterRoles === undefined) {
    return indexedMessages;
  }

  const allowedRoles = new Set(filterRoles.map(normalizeRole));
  return indexedMessages.filter(({ message }) =>
    allowedRoles.has(normalizeRole(message.role)),
  );
}

function normalizeRole(role: string): string {
  return role.trim().toLowerCase() || "unknown";
}

function resolveDefaultCollapsed(
  message: TrajectoryMessage,
  resolver: MessageCollapseResolver | undefined,
): boolean {
  if (typeof resolver === "function") {
    return resolver(message);
  }
  if (typeof resolver === "boolean") {
    return resolver;
  }
  return estimateMessageLength(message) > DEFAULT_AUTO_COLLAPSE_CHAR_LIMIT;
}

function resolveMessageClassName(
  message: TrajectoryMessage,
  originalIndex: number,
  resolver: MessageClassNameResolver | undefined,
): string | undefined {
  if (typeof resolver === "function") {
    return resolver(message, originalIndex);
  }
  return resolver;
}

function estimateMessageLength(message: TrajectoryMessage): number {
  return estimateValueLength(message.content) + estimateValueLength(message.tool_calls);
}

function estimateValueLength(value: unknown): number {
  if (value === undefined || value === null) {
    return 0;
  }
  if (typeof value === "string") {
    return value.length;
  }

  try {
    return JSON.stringify(value).length;
  } catch {
    return String(value).length;
  }
}

function joinClassNames(...names: Array<string | undefined | false>): string {
  return names.filter(Boolean).join(" ");
}
