import type {
  EventRowsContract,
  RunRowsContract,
  RunSnapshotRead,
} from "@/api/types";

export type TraceContractDefinition = RunRowsContract | EventRowsContract;
export type SourceLayout = TraceContractDefinition["source_layout"];
export type SnapshotStatus = RunSnapshotRead["status"];

export type ContractDraft = {
  name: string;
  namedQueryId: number | null;
  sourceLayout: SourceLayout;
  taskId: string;
  trialId: string;
  traceId: string;
  pairingKey: string;
  outcome: string;
  successValues: string;
  failureValues: string;
  abstainValues: string;
  score: string;
  latencyMs: string;
  tokenUsage: string;
  costUsd: string;
  error: string;
  messages: string;
  eventIndex: string;
  role: string;
  content: string;
  kind: string;
  status: string;
  toolCalls: string;
  toolCallId: string;
  nameField: string;
};

export const EMPTY_CONTRACT_DRAFT: ContractDraft = {
  name: "",
  namedQueryId: null,
  sourceLayout: "run_rows",
  taskId: "task_id",
  trialId: "trial_id",
  traceId: "trace_id",
  pairingKey: "pairing_key",
  outcome: "outcome",
  successValues: '["success", true]',
  failureValues: '["failure", false]',
  abstainValues: '["abstain"]',
  score: "score",
  latencyMs: "latency_ms",
  tokenUsage: "token_usage",
  costUsd: "cost_usd",
  error: "error",
  messages: "messages",
  eventIndex: "event_index",
  role: "role",
  content: "content",
  kind: "kind",
  status: "status",
  toolCalls: "tool_calls",
  toolCallId: "tool_call_id",
  nameField: "name",
};
