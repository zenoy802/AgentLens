import { useEffect, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  GripVertical,
  Loader2,
  Pencil,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { useLabelSchema, useSaveLabelSchema } from "@/api/hooks/useLabelSchema";
import type { LabelField } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/common/EmptyState";
import { LoadingState } from "@/components/common/LoadingState";
import { formatApiError } from "@/lib/formatApiError";
import { FieldEditorModal } from "@/features/labeling/FieldEditorModal";

type SchemaEditorDialogProps = {
  open: boolean;
  queryId: number | null;
  onOpenChange: (open: boolean) => void;
};

type FieldEditorState =
  | { mode: "create" }
  | { mode: "edit"; field: LabelField; index: number };

export function SchemaEditorDialog({ open, queryId, onOpenChange }: SchemaEditorDialogProps) {
  const schema = useLabelSchema(open ? queryId : null);
  const saveSchema = useSaveLabelSchema();
  const [fields, setFields] = useState<LabelField[]>([]);
  const [savedFields, setSavedFields] = useState<LabelField[]>([]);
  const [fieldEditor, setFieldEditor] = useState<FieldEditorState | null>(null);
  const schemaReady =
    queryId !== null && schema.isSuccess && schema.data?.query_id === queryId;

  useEffect(() => {
    if (!open || schema.data === undefined) {
      return;
    }

    const nextFields = cloneFields(schema.data.fields);
    setFields(nextFields);
    setSavedFields(cloneFields(schema.data.fields));
  }, [open, schema.data]);

  function handleFieldSubmit(field: LabelField) {
    setFields((current) => {
      if (fieldEditor?.mode !== "edit") {
        return [...current, field];
      }
      return current.map((item, index) => (index === fieldEditor.index ? field : item));
    });
  }

  function moveField(index: number, direction: -1 | 1) {
    setFields((current) => {
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= current.length) {
        return current;
      }
      const next = [...current];
      const [moved] = next.splice(index, 1);
      next.splice(targetIndex, 0, moved);
      return next;
    });
  }

  async function handleSave() {
    if (!schemaReady || saveSchema.isPending) {
      return;
    }

    const validationError = validateSchema(fields);
    if (validationError !== null) {
      toast.error(validationError);
      return;
    }

    const removedKeys = getRemovedKeys(savedFields, fields);
    if (removedKeys.length > 0) {
      const confirmed = window.confirm(
        `你删除了字段：${removedKeys.join(", ")}\n这将清理若干相关打标记录。\n确定保存？`,
      );
      if (!confirmed) {
        return;
      }
    }

    try {
      const result = await saveSchema.mutateAsync({
        queryId,
        fields: cloneFields(fields),
      });
      const nextFields = cloneFields(result.fields);
      setFields(nextFields);
      setSavedFields(cloneFields(result.fields));
      if (result.cascade_deleted_records > 0) {
        toast.success(`Schema 已保存。清理了 ${result.cascade_deleted_records} 条过时打标。`);
      } else {
        toast.success("Schema 已保存");
      }
    } catch {
      // useSaveLabelSchema already reports API errors.
    }
  }

  const fieldEditorOpen = fieldEditor !== null;
  const editingField = fieldEditor?.mode === "edit" ? fieldEditor.field : null;
  const existingKeys = fields.map((field) => field.key);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="grid h-[100dvh] max-h-[100dvh] w-screen max-w-none grid-rows-[auto_minmax(0,1fr)_auto] gap-0 rounded-none p-0 sm:h-[min(760px,92vh)] sm:max-h-[92vh] sm:w-[calc(100vw-2rem)] sm:max-w-4xl sm:rounded-lg">
        <DialogHeader className="border-b p-4 pr-12">
          <DialogTitle>打标字段管理</DialogTitle>
        </DialogHeader>

        <div className="min-h-0 overflow-y-auto p-4">
          {schema.isLoading ? (
            <LoadingState label="正在加载 Schema..." rows={4} className="border-0" />
          ) : schema.isError ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              {formatApiError(schema.error)}
            </div>
          ) : (
            <div className="space-y-4">
              <Button
                variant="outline"
                className="gap-2"
                disabled={!schemaReady}
                onClick={() => setFieldEditor({ mode: "create" })}
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                添加字段
              </Button>

              {fields.length === 0 ? (
                <EmptyState title="暂无字段" className="border-dashed" />
              ) : (
                <div className="space-y-2">
                  {fields.map((field, index) => (
                    <div
                      key={field.key}
                      className="flex items-center gap-3 rounded-md border bg-background p-3"
                    >
                      <GripVertical
                        className="h-4 w-4 shrink-0 text-muted-foreground"
                        aria-hidden="true"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="shrink-0 text-sm text-muted-foreground">
                            {index + 1}.
                          </span>
                          <span className="truncate font-medium">{field.key}</span>
                          <Badge variant="muted">{getTypeLabel(field)}</Badge>
                        </div>
                        <div className="mt-1 truncate text-sm text-muted-foreground">
                          {getFieldSummary(field)}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 px-0"
                          onClick={() => moveField(index, -1)}
                          disabled={index === 0}
                          title="上移"
                        >
                          <ArrowUp className="h-4 w-4" aria-hidden="true" />
                          <span className="sr-only">上移</span>
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 px-0"
                          onClick={() => moveField(index, 1)}
                          disabled={index === fields.length - 1}
                          title="下移"
                        >
                          <ArrowDown className="h-4 w-4" aria-hidden="true" />
                          <span className="sr-only">下移</span>
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="gap-1"
                          onClick={() => setFieldEditor({ mode: "edit", field, index })}
                        >
                          <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                          编辑
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="gap-1 text-destructive hover:text-destructive"
                          onClick={() =>
                            setFields((current) =>
                              current.filter((_, fieldIndex) => fieldIndex !== index),
                            )
                          }
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                          删除
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="border-t p-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
          <Button
            className="gap-2"
            disabled={!schemaReady || schema.isLoading || saveSchema.isPending}
            onClick={() => void handleSave()}
          >
            {saveSchema.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Save className="h-4 w-4" aria-hidden="true" />
            )}
            保存 Schema
          </Button>
        </DialogFooter>

        <FieldEditorModal
          open={fieldEditorOpen}
          field={editingField}
          existingKeys={existingKeys}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) {
              setFieldEditor(null);
            }
          }}
          onSubmit={handleFieldSubmit}
        />
      </DialogContent>
    </Dialog>
  );
}

function cloneFields(fields: LabelField[]): LabelField[] {
  return fields.map((field) => {
    if (field.type === "text") {
      return { ...field };
    }
    return {
      ...field,
      options: getFieldOptions(field).map((option) => ({ ...option })),
    };
  });
}

function getTypeLabel(field: LabelField): string {
  if (field.type === "single_select") {
    return "单选";
  }
  if (field.type === "multi_select") {
    return "多选";
  }
  return "文本";
}

function getFieldSummary(field: LabelField): string {
  if (field.type === "single_select") {
    return `单选 · ${getFieldOptions(field).length} 个选项 · ${field.label}`;
  }
  if (field.type === "multi_select") {
    return `多选 · ${getFieldOptions(field).length} 个选项 · ${field.label}`;
  }
  return `文本 · ${field.label}`;
}

function getRemovedKeys(oldFields: LabelField[], newFields: LabelField[]): string[] {
  const newKeys = new Set(newFields.map((field) => field.key));
  return oldFields.map((field) => field.key).filter((key) => !newKeys.has(key));
}

function validateSchema(fields: LabelField[]): string | null {
  const keys = new Set<string>();
  for (const field of fields) {
    if (keys.has(field.key)) {
      return `字段 key 重复：${field.key}`;
    }
    keys.add(field.key);
    if (field.type === "text") {
      continue;
    }
    const options = getFieldOptions(field);
    if (options.length === 0) {
      return `${field.key} 至少需要 1 个选项`;
    }
    const optionValues = new Set<string>();
    for (const option of options) {
      if (optionValues.has(option.value)) {
        return `${field.key} 的选项 value 重复：${option.value}`;
      }
      optionValues.add(option.value);
    }
  }
  return null;
}

function getFieldOptions(field: LabelField) {
  return field.type === "text" ? [] : (field.options ?? []);
}
