import type { EventRowsContract, RunRowsContract } from "@/api/types";
import type { ContractDraft, TraceContractDefinition } from "@/features/snapshots/types";

type JsonScalar = string | number | boolean | null;

export class ContractDraftError extends Error {}

export function buildContractDefinition(draft: ContractDraft): TraceContractDefinition {
  const base = {
    version: "trace-contract/v1" as const,
    task_id: requiredPath(draft.taskId, "Task ID"),
    trial_id: optionalPath(draft.trialId),
    trace_id: requiredPath(draft.traceId, "Trace ID"),
    pairing_key: optionalPath(draft.pairingKey),
    outcome: requiredPath(draft.outcome, "Outcome"),
    outcome_mapping: {
      success_values: parseScalarArray(draft.successValues, "Success values", true),
      failure_values: parseScalarArray(draft.failureValues, "Failure values", true),
      abstain_values: parseScalarArray(draft.abstainValues, "Abstain values", false),
      case_sensitive: true,
    },
    score: optionalPath(draft.score),
    latency_ms: optionalPath(draft.latencyMs),
    token_usage: optionalPath(draft.tokenUsage),
    cost_usd: optionalPath(draft.costUsd),
    error: optionalPath(draft.error),
    metadata: {},
  };

  if (draft.sourceLayout === "run_rows") {
    const definition: RunRowsContract = {
      ...base,
      source_layout: "run_rows",
      messages: requiredPath(draft.messages, "Messages"),
      message_mapping: {
        role: requiredPath(draft.role, "Message role"),
        content: requiredPath(draft.content, "Message content"),
        name: optionalPath(draft.nameField),
        tool_call_id: optionalPath(draft.toolCallId),
        tool_calls: optionalPath(draft.toolCalls),
        status: optionalPath(draft.status),
      },
    };
    return definition;
  }

  const definition: EventRowsContract = {
    ...base,
    source_layout: "event_rows",
    event_index: requiredPath(draft.eventIndex, "Event index"),
    event_mapping: {
      kind: optionalPath(draft.kind),
      role: optionalPath(draft.role),
      content: requiredPath(draft.content, "Event content"),
      name: optionalPath(draft.nameField),
      tool_call_id: optionalPath(draft.toolCallId),
      tool_calls: optionalPath(draft.toolCalls),
      status: optionalPath(draft.status),
    },
  };
  return definition;
}

export function isSensitiveSampleColumn(column: string): boolean {
  const normalized = column.toLowerCase().replace(/[^a-z0-9]/g, "");
  const markers = [
    "password",
    "passwd",
    "apikey",
    "apitoken",
    "authtoken",
    "bearertoken",
    "secretkey",
    "privatekey",
    "accesstoken",
    "refreshtoken",
    "credential",
    "authorization",
  ];
  return (
    normalized.endsWith("secret") || markers.some((marker) => normalized.includes(marker))
  );
}

export function redactSensitiveSampleValue(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(redactSensitiveSampleValue);
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, nestedValue]) => [
        key,
        isSensitiveSampleColumn(key) ? "[REDACTED]" : redactSensitiveSampleValue(nestedValue),
      ]),
    );
  }
  return value;
}

function requiredPath(value: string, label: string): string {
  const normalized = value.trim();
  if (normalized.length === 0) {
    throw new ContractDraftError(`${label} path is required.`);
  }
  return normalized;
}

function optionalPath(value: string): string | null {
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function parseScalarArray(value: string, label: string, required: boolean): JsonScalar[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new ContractDraftError(`${label} must be a JSON array.`);
  }
  if (!Array.isArray(parsed) || !parsed.every(isJsonScalar)) {
    throw new ContractDraftError(`${label} must contain JSON scalar values only.`);
  }
  if (required && parsed.length === 0) {
    throw new ContractDraftError(`${label} cannot be empty.`);
  }
  return parsed;
}

function isJsonScalar(value: unknown): value is JsonScalar {
  return (
    value === null ||
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  );
}
