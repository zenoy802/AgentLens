import { useState } from "react";
import { Braces, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  useCreateRenderRule,
  useDeleteRenderRule,
  useRenderRules,
  useUpdateRenderRule,
  type RenderRuleCreate,
  type RenderRuleRead,
} from "@/api/hooks/useRenderRules";
import type { FieldRender } from "@/api/types";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatApiError } from "@/lib/formatApiError";

import { RenderRuleFormDialog } from "./RenderRuleFormDialog";

const DEFAULT_RENDER_RULES: RenderRuleCreate[] = [
  {
    match_pattern: "content",
    match_type: "exact",
    render_config: { type: "markdown" },
    priority: 100,
    enabled: true,
  },
  {
    match_pattern: "tool_calls",
    match_type: "exact",
    render_config: { type: "json", collapsed: true },
    priority: 100,
    enabled: true,
  },
  {
    match_pattern: "sql",
    match_type: "exact",
    render_config: { type: "code", language: "sql" },
    priority: 100,
    enabled: true,
  },
  {
    match_pattern: "sql_query",
    match_type: "exact",
    render_config: { type: "code", language: "sql" },
    priority: 100,
    enabled: true,
  },
  {
    match_pattern: "created_at",
    match_type: "exact",
    render_config: { type: "timestamp", format: "YYYY-MM-DD HH:mm:ss" },
    priority: 100,
    enabled: true,
  },
  {
    match_pattern: "updated_at",
    match_type: "exact",
    render_config: { type: "timestamp", format: "YYYY-MM-DD HH:mm:ss" },
    priority: 100,
    enabled: true,
  },
  {
    match_pattern: "messages",
    match_type: "exact",
    render_config: { type: "markdown" },
    priority: 90,
    enabled: true,
  },
  {
    match_pattern: "message",
    match_type: "exact",
    render_config: { type: "markdown" },
    priority: 90,
    enabled: true,
  },
];

export function RenderRulesPanel() {
  const renderRules = useRenderRules();
  const createRule = useCreateRenderRule();
  const updateRule = useUpdateRenderRule();
  const deleteRule = useDeleteRenderRule();

  const [formOpen, setFormOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<RenderRuleRead | null>(null);
  const [deletingRule, setDeletingRule] = useState<RenderRuleRead | null>(null);

  function openCreateDialog() {
    setEditingRule(null);
    setFormOpen(true);
  }

  function openEditDialog(rule: RenderRuleRead) {
    setEditingRule(rule);
    setFormOpen(true);
  }

  async function handleApplyDefaults() {
    try {
      await Promise.all(DEFAULT_RENDER_RULES.map((rule) => createRule.mutateAsync(rule)));
      toast.success("默认规则集已应用");
    } catch (err) {
      toast.error(formatApiError(err));
    }
  }

  async function handleToggleEnabled(rule: RenderRuleRead, enabled: boolean) {
    try {
      await updateRule.mutateAsync({ id: rule.id, payload: { enabled } });
      toast.success(enabled ? "规则已启用" : "规则已停用");
    } catch (err) {
      toast.error(formatApiError(err));
    }
  }

  async function handleDelete() {
    if (deletingRule === null) return;

    try {
      await deleteRule.mutateAsync(deletingRule.id);
      toast.success("渲染规则已删除");
      setDeletingRule(null);
    } catch (err) {
      toast.error(formatApiError(err));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
          全局渲染规则在你执行新 SQL 时自动匹配字段名，建议初始渲染类型。你可以在任何查询的视图配置中覆盖这些建议。
        </p>
        <Button className="w-fit" onClick={openCreateDialog}>
          <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
          新建规则
        </Button>
      </div>

      {renderRules.isLoading ? (
        <LoadingState label="正在加载渲染规则..." rows={5} />
      ) : renderRules.isError || renderRules.data === undefined ? (
        <ErrorState
          error={renderRules.error}
          action={
            <Button variant="outline" size="sm" onClick={() => void renderRules.refetch()}>
              重试
            </Button>
          }
        />
      ) : renderRules.data.length === 0 ? (
        <EmptyState
          icon={<Sparkles className="h-5 w-5" aria-hidden="true" />}
          title="还没有全局渲染规则"
          description="可以先应用默认规则集，再按你的数据字段微调。"
          action={
            <Button onClick={() => void handleApplyDefaults()} disabled={createRule.isPending}>
              <Sparkles className="mr-2 h-4 w-4" aria-hidden="true" />
              应用默认规则集
            </Button>
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-background">
          <Table className="min-w-[760px]">
            <TableHeader>
              <TableRow>
                <TableHead>pattern</TableHead>
                <TableHead>match_type</TableHead>
                <TableHead>render_config</TableHead>
                <TableHead>priority</TableHead>
                <TableHead>enabled</TableHead>
                <TableHead className="w-[180px] text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {renderRules.data.map((rule) => (
                <TableRow key={rule.id}>
                  <TableCell>
                    <code className="break-all rounded bg-muted px-1.5 py-0.5 text-xs">
                      {rule.match_pattern}
                    </code>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{rule.match_type}</Badge>
                  </TableCell>
                  <TableCell>{renderConfigPreview(rule.render_config)}</TableCell>
                  <TableCell>{rule.priority}</TableCell>
                  <TableCell>
                    <Switch
                      checked={rule.enabled}
                      disabled={updateRule.isPending}
                      onCheckedChange={(checked) =>
                        void handleToggleEnabled(rule, checked)
                      }
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openEditDialog(rule)}
                      >
                        <Pencil className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                        编辑
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => setDeletingRule(rule)}
                      >
                        <Trash2 className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                        删除
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <RenderRuleFormDialog
        open={formOpen}
        rule={editingRule}
        onOpenChange={setFormOpen}
      />

      <Dialog open={deletingRule !== null} onOpenChange={(open) => !open && setDeletingRule(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <div className="flex items-center gap-2">
              <Braces className="h-5 w-5 text-destructive" aria-hidden="true" />
              <DialogTitle>删除渲染规则</DialogTitle>
            </div>
            <DialogDescription>删除后，新查询不会再使用这条全局建议。</DialogDescription>
          </DialogHeader>

          {deletingRule !== null ? (
            <p className="text-sm text-muted-foreground">
              确认删除{" "}
              <span className="font-medium text-foreground">
                {deletingRule.match_pattern}
              </span>{" "}
              规则？
            </p>
          ) : null}

          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingRule(null)}>
              取消
            </Button>
            <Button
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteRule.isPending}
              onClick={() => void handleDelete()}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function renderConfigPreview(renderConfig: FieldRender): string {
  if (renderConfig.type === "code") {
    return `code(${renderConfig.language ?? "plain"})`;
  }
  if (renderConfig.type === "json") {
    return renderConfig.collapsed ? "json(collapsed)" : "json(expanded)";
  }
  if (renderConfig.type === "timestamp") {
    return `timestamp(${renderConfig.format ?? "YYYY-MM-DD HH:mm:ss"})`;
  }
  return renderConfig.type;
}
