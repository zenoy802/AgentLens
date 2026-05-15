import type { Trajectory, TrajectoryMessage } from "@/api/types";
import { normalizeTrajectoryRole } from "@/features/trajectory-view/trajectoryRoles";

export interface GenerateComparisonMarkdownOptions {
  roleFilter?: string[];
}

export function generateComparisonMarkdown(
  trajectories: Trajectory[],
  opts: GenerateComparisonMarkdownOptions = {},
): string {
  const allowedRoles =
    opts.roleFilter === undefined
      ? null
      : new Set(opts.roleFilter.map((role) => normalizeTrajectoryRole(role)));

  const sections = trajectories.map((trajectory, index) => {
    const title = `# Trajectory ${index + 1}: ${escapeMarkdownText(trajectory.group_key)}`;
    const messages = trajectory.messages.filter((message) =>
      allowedRoles === null
        ? true
        : allowedRoles.has(normalizeTrajectoryRole(message.role)),
    );

    if (messages.length === 0) {
      return `${title}\n\n_No messages matched the selected role filter._`;
    }

    return `${title}\n\n${messages.map(formatMessage).join("\n\n")}`;
  });

  return `${sections.join("\n\n")}\n`;
}

function formatMessage(message: TrajectoryMessage, index: number): string {
  const parts = [
    `## ${index + 1}. ${escapeMarkdownText(message.role.trim() || "unknown")}`,
  ];
  const content = escapeMarkdownText(formatValue(message.content));
  const toolCalls = formatToolCalls(message);

  if (content.length > 0) {
    parts.push("", content);
  }
  if (toolCalls.length > 0) {
    parts.push("", toolCalls);
  }

  return parts.join("\n");
}

function formatToolCalls(message: TrajectoryMessage): string {
  if (message.tool_calls === undefined || message.tool_calls === null) {
    return "";
  }

  return [
    "### Tool calls",
    "",
    "```json",
    stringifyJson(message.tool_calls),
    "```",
  ].join("\n");
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  return stringifyJson(value);
}

function stringifyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function escapeMarkdownText(value: string): string {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\|/g, "\\|")
    .replace(/([*_`~#[\]()!+{}.-])/g, "\\$1");
}
