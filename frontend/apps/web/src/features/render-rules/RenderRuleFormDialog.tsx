import { FormEvent, useEffect, useMemo, useState } from "react";
import { AlertCircle, Braces, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";

import {
  useCreateRenderRule,
  useUpdateRenderRule,
  type RenderRuleCreate,
  type RenderRuleRead,
} from "@/api/hooks/useRenderRules";
import type { RenderRuleConfig } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { formatApiError } from "@/lib/formatApiError";

import type {
  CodeLanguage,
  MatchType,
  RenderRuleFormValues,
  RenderRuleTarget,
  RenderType,
  TrajectoryRuleField,
} from "./types";

type RenderRuleFormDialogProps = {
  open: boolean;
  rule: RenderRuleRead | null;
  onOpenChange: (open: boolean) => void;
};

const MATCH_TYPES: MatchType[] = ["exact", "prefix", "suffix", "regex"];
const RULE_TARGETS: RenderRuleTarget[] = ["field_render", "trajectory_config"];
const RENDER_TYPES: RenderType[] = ["text", "markdown", "json", "code", "timestamp", "tag"];
const CODE_LANGUAGES: CodeLanguage[] = ["sql", "python", "javascript", "json", "plain"];
const TRAJECTORY_FIELDS: TrajectoryRuleField[] = [
  "group_by",
  "role_column",
  "content_column",
  "tool_calls_column",
  "order_by",
];
const DEFAULT_TIMESTAMP_FORMAT = "YYYY-MM-DD HH:mm:ss";

const DEFAULT_VALUES: RenderRuleFormValues = {
  matchPattern: "",
  matchType: "exact",
  target: "field_render",
  renderType: "text",
  codeLanguage: "plain",
  jsonCollapsed: true,
  timestampFormat: DEFAULT_TIMESTAMP_FORMAT,
  trajectoryField: "content_column",
  trajectoryOrderDirection: "asc",
  priority: 0,
  enabled: true,
};

export function RenderRuleFormDialog({
  open,
  rule,
  onOpenChange,
}: RenderRuleFormDialogProps) {
  const createRule = useCreateRenderRule();
  const updateRule = useUpdateRenderRule();

  const [values, setValues] = useState<RenderRuleFormValues>(DEFAULT_VALUES);
  const [sampleFieldName, setSampleFieldName] = useState("");

  const isEditMode = rule !== null;

  useEffect(() => {
    if (!open) return;

    if (rule === null) {
      setValues(DEFAULT_VALUES);
      setSampleFieldName("");
      return;
    }

    setValues(valuesFromRule(rule));
    setSampleFieldName(rule.match_pattern);
  }, [open, rule]);

  const matchResult = useMemo(
    () => testMatch(values.matchPattern, values.matchType, sampleFieldName),
    [sampleFieldName, values.matchPattern, values.matchType],
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const payload: RenderRuleCreate = {
      match_pattern: values.matchPattern.trim(),
      match_type: values.matchType,
      render_config: buildRenderConfig(values),
      priority: values.priority,
      enabled: values.enabled,
    };

    try {
      if (isEditMode) {
        await updateRule.mutateAsync({ id: rule.id, payload });
        toast.success("渲染规则已更新");
      } else {
        await createRule.mutateAsync(payload);
        toast.success("渲染规则已创建");
      }
      onOpenChange(false);
    } catch (err) {
      toast.error(formatApiError(err));
    }
  }

  function updateValues(patch: Partial<RenderRuleFormValues>) {
    setValues((current) => ({ ...current, ...patch }));
  }

  const isPending = createRule.isPending || updateRule.isPending;
  const canSubmit = values.matchPattern.trim().length > 0 && !isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Braces className="h-5 w-5" aria-hidden="true" />
            <DialogTitle>{isEditMode ? "编辑规则" : "新建规则"}</DialogTitle>
          </div>
          <DialogDescription>
            配置字段名匹配方式，并用于表格字段渲染或 Trajectory 聚合字段建议。
          </DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block text-sm font-medium">
              Pattern
              <input
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                value={values.matchPattern}
                onChange={(event) =>
                  updateValues({ matchPattern: event.target.value })
                }
                maxLength={200}
                required
                placeholder="content"
              />
            </label>

            <label className="block text-sm font-medium">
              Match Type
              <Select
                value={values.matchType}
                onValueChange={(value) =>
                  updateValues({ matchType: value as MatchType })
                }
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MATCH_TYPES.map((matchType) => (
                    <SelectItem key={matchType} value={matchType}>
                      {matchType}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
          </div>

          <label className="block text-sm font-medium">
            Rule Target
            <Select
              value={values.target}
              onValueChange={(value) =>
                updateValues({ target: value as RenderRuleTarget })
              }
            >
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RULE_TARGETS.map((target) => (
                  <SelectItem key={target} value={target}>
                    {target === "field_render" ? "Table field render" : "Trajectory config"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>

          <div className="rounded-md border bg-muted/30 p-3">
            <label className="block text-sm font-medium">
              示例字段名
              <input
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                value={sampleFieldName}
                onChange={(event) => setSampleFieldName(event.target.value)}
                placeholder="meta_json"
              />
            </label>
            <div className="mt-2 flex items-center gap-2 text-sm">
              {matchResult.tone === "success" ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
              ) : matchResult.tone === "warning" ? (
                <AlertCircle className="h-4 w-4 text-amber-600" aria-hidden="true" />
              ) : (
                <XCircle className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              )}
              <span className={matchToneClassName(matchResult.tone)}>
                {sampleFieldName.trim().length === 0
                  ? "输入示例字段名后显示匹配结果"
                  : matchResult.label}
              </span>
            </div>
          </div>

          {values.target === "field_render" ? (
            <div className="grid gap-3 md:grid-cols-2">
              <label className="block text-sm font-medium">
                Render Type
                <Select
                  value={values.renderType}
                  onValueChange={(value) =>
                    updateValues({ renderType: value as RenderType })
                  }
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RENDER_TYPES.map((renderType) => (
                      <SelectItem key={renderType} value={renderType}>
                        {renderType}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>

              {values.renderType === "code" ? (
                <label className="block text-sm font-medium">
                  语言
                  <Select
                    value={values.codeLanguage}
                    onValueChange={(value) =>
                      updateValues({ codeLanguage: value as CodeLanguage })
                    }
                  >
                    <SelectTrigger className="mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CODE_LANGUAGES.map((language) => (
                        <SelectItem key={language} value={language}>
                          {language}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </label>
              ) : null}

              {values.renderType === "json" ? (
                <div className="flex items-center justify-between rounded-md border bg-background px-3 py-2">
                  <div className="text-sm font-medium">默认折叠</div>
                  <Switch
                    checked={values.jsonCollapsed}
                    onCheckedChange={(checked) =>
                      updateValues({ jsonCollapsed: checked })
                    }
                  />
                </div>
              ) : null}

              {values.renderType === "timestamp" ? (
                <label className="block text-sm font-medium">
                  格式
                  <input
                    className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                    value={values.timestampFormat}
                    onChange={(event) =>
                      updateValues({ timestampFormat: event.target.value })
                    }
                    placeholder={DEFAULT_TIMESTAMP_FORMAT}
                  />
                </label>
              ) : null}
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              <label className="block text-sm font-medium">
                Trajectory Field
                <Select
                  value={values.trajectoryField}
                  onValueChange={(value) =>
                    updateValues({ trajectoryField: value as TrajectoryRuleField })
                  }
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TRAJECTORY_FIELDS.map((field) => (
                      <SelectItem key={field} value={field}>
                        {field}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>

              {values.trajectoryField === "order_by" ? (
                <label className="block text-sm font-medium">
                  Order Direction
                  <Select
                    value={values.trajectoryOrderDirection}
                    onValueChange={(value) => {
                      if (value === "asc" || value === "desc") {
                        updateValues({ trajectoryOrderDirection: value });
                      }
                    }}
                  >
                    <SelectTrigger className="mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="asc">asc</SelectItem>
                      <SelectItem value="desc">desc</SelectItem>
                    </SelectContent>
                  </Select>
                </label>
              ) : null}
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            <label className="block text-sm font-medium">
              Priority
              <input
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                type="number"
                value={values.priority}
                onChange={(event) =>
                  updateValues({ priority: Number(event.target.value) })
                }
              />
            </label>

            <div className="flex items-center justify-between rounded-md border bg-background px-3 py-2">
              <div className="text-sm font-medium">Enabled</div>
              <Switch
                checked={values.enabled}
                onCheckedChange={(checked) => updateValues({ enabled: checked })}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {isEditMode ? "保存" : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function valuesFromRule(rule: RenderRuleRead): RenderRuleFormValues {
  const renderConfig = rule.render_config;
  if (renderConfig.type === "trajectory_config") {
    return {
      matchPattern: rule.match_pattern,
      matchType: rule.match_type,
      target: "trajectory_config",
      renderType: "text",
      codeLanguage: "plain",
      jsonCollapsed: true,
      timestampFormat: DEFAULT_TIMESTAMP_FORMAT,
      trajectoryField: renderConfig.field,
      trajectoryOrderDirection: renderConfig.order_direction ?? "asc",
      priority: rule.priority,
      enabled: rule.enabled,
    };
  }

  return {
    matchPattern: rule.match_pattern,
    matchType: rule.match_type,
    target: "field_render",
    renderType: renderConfig.type,
    codeLanguage:
      renderConfig.type === "code" && isCodeLanguage(renderConfig.language)
        ? renderConfig.language
        : "plain",
    jsonCollapsed: renderConfig.type === "json" ? renderConfig.collapsed ?? true : true,
    timestampFormat:
      renderConfig.type === "timestamp"
        ? renderConfig.format ?? DEFAULT_TIMESTAMP_FORMAT
        : DEFAULT_TIMESTAMP_FORMAT,
    trajectoryField: "content_column",
    trajectoryOrderDirection: "asc",
    priority: rule.priority,
    enabled: rule.enabled,
  };
}

function buildRenderConfig(values: RenderRuleFormValues): RenderRuleConfig {
  if (values.target === "trajectory_config") {
    return {
      type: "trajectory_config",
      field: values.trajectoryField,
      order_direction:
        values.trajectoryField === "order_by" ? values.trajectoryOrderDirection : null,
    };
  }

  switch (values.renderType) {
    case "markdown":
      return { type: "markdown" };
    case "json":
      return { type: "json", collapsed: values.jsonCollapsed };
    case "code":
      return { type: "code", language: values.codeLanguage };
    case "timestamp":
      return {
        type: "timestamp",
        format: values.timestampFormat.trim() || DEFAULT_TIMESTAMP_FORMAT,
      };
    case "tag":
      return { type: "tag" };
    case "text":
      return { type: "text" };
  }
}

function testMatch(
  pattern: string,
  matchType: MatchType,
  sample: string,
): MatchPreviewResult {
  if (sample.trim().length === 0) {
    return { matches: false, label: "未匹配", tone: "muted" };
  }

  if (matchType === "exact") {
    return labelMatch(sample === pattern);
  }
  if (matchType === "prefix") {
    return labelMatch(sample.startsWith(pattern));
  }
  if (matchType === "suffix") {
    return labelMatch(sample.endsWith(pattern));
  }

  try {
    const preview = buildRegexPreview(pattern);
    if (preview.type === "unsupported") {
      return {
        matches: false,
        label: "浏览器无法预览该 Python regex；保存时由后端校验",
        tone: "warning",
      };
    }
    return labelMatch(regexFullMatches(preview.regex, sample));
  } catch {
    return { matches: false, label: "regex 无效", tone: "muted" };
  }
}

type MatchPreviewResult = {
  matches: boolean;
  label: string;
  tone: "success" | "muted" | "warning";
};

type RegexPreview =
  | {
      type: "regex";
      regex: RegExp;
    }
  | {
      type: "unsupported";
    };

function buildRegexPreview(pattern: string): RegexPreview {
  const inlineFlags = parsePythonInlineFlags(pattern);
  if (inlineFlags?.supported === false) {
    return { type: "unsupported" };
  }

  const body = inlineFlags === null ? pattern : pattern.slice(inlineFlags.raw.length);
  const flags = inlineFlags === null ? "" : inlineFlags.flags;
  if (hasPythonOnlyRegexToken(body)) {
    return { type: "unsupported" };
  }

  try {
    return { type: "regex", regex: new RegExp(body, flags) };
  } catch (err) {
    if (pattern.includes("(?")) {
      return { type: "unsupported" };
    }
    throw err;
  }
}

function regexFullMatches(regex: RegExp, sample: string): boolean {
  const match = regex.exec(sample);
  return match !== null && match.index === 0 && match[0] === sample;
}

const PYTHON_ONLY_PREVIEW_TOKENS = new Set(["A", "Z", "w", "W", "d", "D", "b", "B"]);

function hasPythonOnlyRegexToken(pattern: string): boolean {
  for (let index = 0; index < pattern.length - 1; index += 1) {
    if (pattern[index] !== "\\" || !PYTHON_ONLY_PREVIEW_TOKENS.has(pattern[index + 1])) {
      continue;
    }
    if (countBackslashRunEndingAt(pattern, index) % 2 === 1) {
      return true;
    }
  }
  return false;
}

function countBackslashRunEndingAt(pattern: string, index: number): number {
  let count = 0;
  for (let cursor = index; cursor >= 0 && pattern[cursor] === "\\"; cursor -= 1) {
    count += 1;
  }
  return count;
}

function parsePythonInlineFlags(
  pattern: string,
): { supported: true; raw: string; flags: string } | { supported: false } | null {
  const match = pattern.match(/^\(\?([aiLmsux]+)\)/);
  if (match === null) {
    return null;
  }

  const flags = new Set<string>();
  for (const flag of match[1]) {
    if (flag === "i" || flag === "m" || flag === "s") {
      flags.add(flag);
    } else if (flag === "u") {
      continue;
    } else {
      return { supported: false };
    }
  }

  return { supported: true, raw: match[0], flags: [...flags].join("") };
}

function labelMatch(matches: boolean): MatchPreviewResult {
  return {
    matches,
    label: matches ? "匹配" : "不匹配",
    tone: matches ? "success" : "muted",
  };
}

function matchToneClassName(tone: MatchPreviewResult["tone"]): string {
  if (tone === "success") {
    return "text-emerald-700";
  }
  if (tone === "warning") {
    return "text-amber-700";
  }
  return "text-muted-foreground";
}

function isCodeLanguage(value: string): value is CodeLanguage {
  return CODE_LANGUAGES.includes(value as CodeLanguage);
}
