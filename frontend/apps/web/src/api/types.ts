import type { components, operations, paths } from "@/api/types.gen";

export type { components, operations, paths };

type Schemas = components["schemas"];

export type AdminInfoResponse = Schemas["AdminInfoResponse"];
export type CleanupReport = Schemas["CleanupReport"];
export type CleanupRequest = Schemas["CleanupRequest"];
export type Column = Schemas["ColumnRead"];
export type ConnectionCreate = Schemas["ConnectionCreate"];
export type ConnectionListResponse = Schemas["ConnectionListResponse"];
export type ConnectionRead = Schemas["ConnectionRead"];
export type ConnectionTestResponse = Schemas["ConnectionTestResponse"];
export type ConnectionUpdate = Schemas["ConnectionUpdate"];
export type ExecuteRequest = Schemas["ExecuteRequest"];
export type ExportRequest = Schemas["ExportRequest"];
export type ExecutionInfo = Schemas["ExecutionInfo"];
export type FieldRender =
  | Schemas["TextRender"]
  | Schemas["MarkdownRender"]
  | Schemas["JsonRender"]
  | Schemas["CodeRender"]
  | Schemas["TimestampRender"]
  | Schemas["TagRender"];
export type HealthResponse = Schemas["HealthResponse"];
export type HTTPValidationError = Schemas["HTTPValidationError"];
export type NamedQueryCreate = Schemas["NamedQueryCreate"];
export type NamedQueryListResponse = Schemas["NamedQueryListResponse"];
export type NamedQueryPromote = Schemas["NamedQueryPromote"];
export type NamedQueryRead = Schemas["NamedQueryRead"];
export type NamedQueryUpdate = Schemas["NamedQueryUpdate"];
export type Pagination = Schemas["Pagination"];
export type QueryExecuteRequest = Schemas["QueryExecuteRequest"];
export type QueryHistoryListResponse = Schemas["QueryHistoryListResponse"];
export type QueryHistoryRead = Schemas["QueryHistoryRead"];
export type RenderRuleCreate = Schemas["RenderRuleCreate"];
export type RenderRuleRead = Schemas["RenderRuleRead"];
export type RenderRuleUpdate = Schemas["RenderRuleUpdate"];
export type SchedulerJobRead = Schemas["SchedulerJobRead"];
export type Trajectory = Schemas["Trajectory"];
export type TrajectoryAggregateRequest = Schemas["TrajectoryAggregateRequest"];
export type TrajectoryAggregateResponse = Schemas["TrajectoryAggregateResponse"];
export type TrajectoryConfig = Schemas["TrajectoryConfig"];
export type TrajectoryMessage = Schemas["TrajectoryMessage"];
export type ValidationError = Schemas["ValidationError"];
export type ViewConfigPayload = Schemas["ViewConfigPayload"];
export type ViewConfigRead = Schemas["ViewConfigRead"];
export type Warning = Schemas["WarningRead"];
export type WarningRead = Schemas["WarningRead"];

export type Row = Record<string, unknown>;
export type ExecutionResult = Omit<Schemas["ExecutionResult"], "rows"> & {
  rows: Row[];
};
