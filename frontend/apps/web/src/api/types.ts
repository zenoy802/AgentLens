import type { components, operations, paths } from "@/api/types.gen";

export type { components, operations, paths };

type Schemas = components["schemas"];

export type AdminInfoResponse = Schemas["AdminInfoResponse"];
export type Annotation = Schemas["AnnotationOut"];
export type AnnotationColor = Schemas["AnnotationColor"];
export type AnnotationCreate = Schemas["AnnotationCreate"];
export type AnnotationSeverity = Schemas["AnnotationSeverity"];
export type AnnotationFilters =
  operations["list_annotations_api_v1_queries__query_id__annotations_get"]["parameters"]["query"];
export type AnnotationClearFilters =
  operations["delete_annotations_api_v1_queries__query_id__annotations_delete"]["parameters"]["query"];
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
export type ExecutionFingerprints = Schemas["ExecutionFingerprints"];
export type ExecutionInfo = Schemas["ExecutionInfo"];
export type FieldRender =
  | Schemas["TextRender"]
  | Schemas["MarkdownRender"]
  | Schemas["JsonRender"]
  | Schemas["CodeRender"]
  | Schemas["TimestampRender"]
  | Schemas["TagRender"]
  | Schemas["EnumRender"];
export type HealthResponse = Schemas["HealthResponse"];
export type HTTPValidationError = Schemas["HTTPValidationError"];
export type LabelField =
  | Schemas["SingleSelectField"]
  | Schemas["MultiSelectField"]
  | Schemas["TextField"];
export type LabelOption = Schemas["LabelOption"];
export type LabelBatchResult = Schemas["LabelBatchResult"];
export type LabelBatchUpsert = Schemas["LabelBatchUpsert"];
export type LabelRecordRead = Schemas["LabelRecordRead"];
export type LabelRecordUpsert = Schemas["LabelRecordUpsert"];
export type LabelRowsQuery = Schemas["LabelRowsQuery"];
export type LabelSchemaPayload = Schemas["LabelSchemaPayload"];
export type LabelSchemaRead = Schemas["LabelSchemaRead"];
export type LabelsByRowResponse = Schemas["LabelsByRowResponse"];
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
export type SelectionSnapshot = Schemas["SelectionSnapshotOut"];
export type SelectionSnapshotCreate = Schemas["SelectionSnapshotCreate"];
export type Trajectory = Schemas["Trajectory"];
export type TrajectoryAggregateRequest = Schemas["TrajectoryAggregateRequest"];
export type TrajectoryAggregateResponse = Schemas["TrajectoryAggregateResponse"];
export type TrajectoryConfig = Schemas["TrajectoryConfig"];
export type TrajectoryConfigRule = Schemas["TrajectoryConfigRule"];
export type TrajectoryMessage = Schemas["TrajectoryMessage"];
export type ValidationError = Schemas["ValidationError"];
export type ViewConfigPayload = Schemas["ViewConfigPayload"];
export type ViewConfigRead = Schemas["ViewConfigRead"];
export type Warning = Schemas["WarningRead"];
export type WarningRead = Schemas["WarningRead"];
export type CanonicalRunRow = Schemas["CanonicalRunRow"];
export type EventRowsContract = Schemas["EventRowsContract"];
export type RunRowsContract = Schemas["RunRowsContract"];
export type RunSnapshotCreate = Schemas["RunSnapshotCreate"];
export type RunSnapshotListResponse = Schemas["RunSnapshotListResponse"];
export type RunSnapshotRead = Schemas["RunSnapshotRead"];
export type RunSnapshotStatusRead = Schemas["RunSnapshotStatusRead"];
export type SnapshotBuildPolicy = Schemas["SnapshotBuildPolicy"];
export type TraceContractCreate = Schemas["TraceContractCreate"];
export type TraceContractListResponse = Schemas["TraceContractListResponse"];
export type TraceContractRead = Schemas["TraceContractRead"];
export type TraceContractValidateRequest = Schemas["TraceContractValidateRequest"];
export type TraceContractValidationResult = Schemas["TraceContractValidationResult"];

export type Row = Record<string, unknown>;
export type QueryFingerprints = ExecutionFingerprints;
export type RenderRuleConfig = FieldRender | TrajectoryConfigRule;
export type ExecutionResult = Omit<Schemas["ExecutionResult"], "rows"> & {
  rows: Row[];
};
