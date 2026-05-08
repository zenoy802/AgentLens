import { MessageBubble } from "./MessageBubble";
import type { TrajectoryMessage, TrajectoryViewerProps } from "./types";

import "./styles.css";

export function TrajectoryViewer({
  trajectory,
  renderContent,
  renderToolCalls,
  filterRoles,
  className,
  messageClassName,
  showHeader = true,
  showMetaLine = false,
  metaFields,
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
        {messages.map((message, index) => (
          <MessageBubble
            key={`${message.row_identity}:${index}`}
            message={message}
            renderContent={renderContent}
            renderToolCalls={renderToolCalls}
            showMetaLine={showMetaLine}
            metaFields={metaFields}
            className={messageClassName}
          />
        ))}
      </div>
    </section>
  );
}

function filterMessagesByRole(
  messages: TrajectoryMessage[],
  filterRoles: string[] | undefined,
): TrajectoryMessage[] {
  if (filterRoles === undefined) {
    return messages;
  }

  const allowedRoles = new Set(filterRoles.map(normalizeRole));
  return messages.filter((message) =>
    allowedRoles.has(normalizeRole(message.role)),
  );
}

function normalizeRole(role: string): string {
  return role.trim().toLowerCase() || "unknown";
}

function joinClassNames(...names: Array<string | undefined | false>): string {
  return names.filter(Boolean).join(" ");
}
