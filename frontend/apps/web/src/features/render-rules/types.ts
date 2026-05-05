import type { FieldRender } from "@/api/types";

export type MatchType = "exact" | "prefix" | "suffix" | "regex";
export type RenderType = FieldRender["type"];
export type CodeLanguage = "sql" | "python" | "javascript" | "json" | "plain";

export type RenderRuleFormValues = {
  matchPattern: string;
  matchType: MatchType;
  renderType: RenderType;
  codeLanguage: CodeLanguage;
  jsonCollapsed: boolean;
  timestampFormat: string;
  priority: number;
  enabled: boolean;
};
