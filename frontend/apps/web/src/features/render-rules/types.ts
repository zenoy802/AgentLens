import type { FieldRender, RenderRuleConfig } from "@/api/types";

export type MatchType = "exact" | "prefix" | "suffix" | "regex";
export type RenderType = FieldRender["type"];
export type CodeLanguage = "sql" | "python" | "javascript" | "json" | "plain";
export type RenderRuleTarget = "field_render" | "trajectory_config";
export type TrajectoryRuleField = Extract<
  RenderRuleConfig,
  { type: "trajectory_config" }
>["field"];

export type RenderRuleFormValues = {
  matchPattern: string;
  matchType: MatchType;
  target: RenderRuleTarget;
  renderType: RenderType;
  codeLanguage: CodeLanguage;
  jsonCollapsed: boolean;
  timestampFormat: string;
  trajectoryField: TrajectoryRuleField;
  trajectoryOrderDirection: "asc" | "desc";
  priority: number;
  enabled: boolean;
};
