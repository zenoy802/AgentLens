import { useEffect, useState, type ReactNode } from "react";
import { Info, Plus, X } from "lucide-react";

import type { LabelField, LabelOption } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

type LabelFieldType = LabelField["type"];

type OptionDraft = {
  id: string;
  value: string;
  label: string;
  color: string | null;
};

type FieldDraft = {
  key: string;
  label: string;
  type: LabelFieldType;
  options: OptionDraft[];
};

type FieldErrors = {
  key?: string;
  label?: string;
  options?: string;
};

type FieldEditorModalProps = {
  open: boolean;
  field: LabelField | null;
  existingKeys: string[];
  onOpenChange: (open: boolean) => void;
  onSubmit: (field: LabelField) => void;
};

const KEY_PATTERN = /^[a-z][a-z0-9_]*$/;

const COLOR_PALETTE = [
  { name: "emerald", value: "#10b981" },
  { name: "amber", value: "#f59e0b" },
  { name: "rose", value: "#f43f5e" },
  { name: "indigo", value: "#6366f1" },
  { name: "sky", value: "#0ea5e9" },
  { name: "violet", value: "#8b5cf6" },
  { name: "cyan", value: "#06b6d4" },
  { name: "lime", value: "#84cc16" },
  { name: "slate", value: "#64748b" },
  { name: "red", value: "#ef4444" },
] as const;

export function FieldEditorModal({
  open,
  field,
  existingKeys,
  onOpenChange,
  onSubmit,
}: FieldEditorModalProps) {
  const [draft, setDraft] = useState<FieldDraft>(() => createDraft(field));
  const [errors, setErrors] = useState<FieldErrors>({});
  const isEditing = field !== null;
  const originalKey = field?.key ?? null;
  const liveKeyError =
    draft.key.trim().length > 0 ? validateKey(draft.key, existingKeys, originalKey) : undefined;

  useEffect(() => {
    if (open) {
      setDraft(createDraft(field));
      setErrors({});
    }
  }, [field, open]);

  function handleTypeChange(value: string) {
    if (!isLabelFieldType(value)) {
      return;
    }

    setDraft((current) => ({
      ...current,
      type: value,
      options:
        value === "text"
          ? current.options
          : current.options.length > 0
            ? current.options
            : [createOptionDraft()],
    }));
    setErrors((current) => ({ ...current, options: undefined }));
  }

  function updateOption(index: number, patch: Partial<OptionDraft>) {
    setDraft((current) => ({
      ...current,
      options: current.options.map((option, optionIndex) =>
        optionIndex === index ? { ...option, ...patch } : option,
      ),
    }));
  }

  function removeOption(index: number) {
    setDraft((current) => ({
      ...current,
      options: current.options.filter((_, optionIndex) => optionIndex !== index),
    }));
  }

  function handleSubmit() {
    const nextErrors = validateDraft(draft, existingKeys, originalKey);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    onSubmit(buildField(draft));
    onOpenChange(false);
  }

  const keyError = errors.key ?? liveKeyError;
  const selectOptionsVisible = draft.type !== "text";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEditing ? "编辑字段" : "添加字段"}</DialogTitle>
        </DialogHeader>

        <div className="max-h-[70vh] space-y-5 overflow-y-auto pr-1">
          <div className="rounded-md border bg-muted/30 p-3 text-sm">
            <div className="flex gap-2">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <div className="space-y-1 text-muted-foreground">
                <p>
                  Key 是稳定的内部标识，用于保存、导出和筛选；Label 是展示给用户看的字段名称。
                </p>
                <p>
                  例如：Key 填 <code className="rounded bg-background px-1">quality</code>，
                  Label 填 <code className="rounded bg-background px-1">回答质量</code>。
                </p>
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <FieldControl
              label="字段 Key（内部标识）*"
              description="保存后不可修改。只能用小写字母、数字、下划线，且必须以字母开头。"
            >
              <Input
                value={draft.key}
                disabled={isEditing}
                placeholder="quality"
                onChange={(event) => {
                  setDraft((current) => ({ ...current, key: event.target.value }));
                  setErrors((current) => ({ ...current, key: undefined }));
                }}
              />
              {keyError !== undefined ? <ErrorText>{keyError}</ErrorText> : null}
            </FieldControl>

            <FieldControl
              label="显示名称 Label*"
              description="展示在表格列、行详情和打标统计中，可以使用中文。"
            >
              <Input
                value={draft.label}
                placeholder="回答质量"
                onChange={(event) => {
                  setDraft((current) => ({ ...current, label: event.target.value }));
                  setErrors((current) => ({ ...current, label: undefined }));
                }}
              />
              {errors.label !== undefined ? <ErrorText>{errors.label}</ErrorText> : null}
            </FieldControl>
          </div>

          <FieldControl label="字段类型">
            <Select value={draft.type} onValueChange={handleTypeChange}>
              <SelectTrigger className="max-w-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="single_select">单选</SelectItem>
                <SelectItem value="multi_select">多选</SelectItem>
                <SelectItem value="text">文本</SelectItem>
              </SelectContent>
            </Select>
          </FieldControl>

          {selectOptionsVisible ? (
            <div className="space-y-3 border-t pt-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-sm font-medium">选项</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    Value 是实际保存的选项值；Label 是用户在打标时看到的选项文案。
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={() =>
                    setDraft((current) => ({
                      ...current,
                      options: [...current.options, createOptionDraft()],
                    }))
                  }
                >
                  <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  添加选项
                </Button>
              </div>

              {errors.options !== undefined ? <ErrorText>{errors.options}</ErrorText> : null}

              <div className="space-y-3">
                {draft.options.map((option, index) => (
                  <div key={option.id} className="rounded-md border p-3">
                    <div className="grid gap-3 lg:grid-cols-[1fr_1fr_auto_auto] lg:items-end">
                      <FieldControl
                        label="选项值 Value"
                        description="用于保存和导出，建议使用小写英文或短代码。"
                      >
                        <Input
                          value={option.value}
                          placeholder="good"
                          onChange={(event) => {
                            updateOption(index, { value: event.target.value });
                            setErrors((current) => ({ ...current, options: undefined }));
                          }}
                        />
                      </FieldControl>
                      <FieldControl
                        label="显示文案 Label"
                        description="展示在下拉选项、统计和筛选里。"
                      >
                        <Input
                          value={option.label}
                          placeholder="好"
                          onChange={(event) =>
                            updateOption(index, { label: event.target.value })
                          }
                        />
                      </FieldControl>
                      <ColorPicker
                        color={option.color}
                        onChange={(color) => updateOption(index, { color })}
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-9 w-9 px-0 text-muted-foreground"
                        onClick={() => removeOption(index)}
                        title="删除选项"
                      >
                        <X className="h-4 w-4" aria-hidden="true" />
                        <span className="sr-only">删除选项</span>
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit}>{isEditing ? "保存字段" : "添加字段"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FieldControl({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Label className="grid gap-2">
      <span>{label}</span>
      {description !== undefined ? (
        <span className="text-xs font-normal leading-5 text-muted-foreground">
          {description}
        </span>
      ) : null}
      {children}
    </Label>
  );
}

function ErrorText({ children }: { children: ReactNode }) {
  return <span className="text-xs font-medium text-destructive">{children}</span>;
}

function ColorPicker({
  color,
  onChange,
}: {
  color: string | null;
  onChange: (color: string | null) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">颜色</div>
      <div className="flex max-w-[15rem] flex-wrap gap-1.5">
        <button
          type="button"
          className={cn(
            "h-7 rounded-md border px-2 text-xs",
            color === null ? "border-primary bg-primary text-primary-foreground" : "bg-background",
          )}
          onClick={() => onChange(null)}
        >
          无
        </button>
        {COLOR_PALETTE.map((item) => (
          <button
            key={item.name}
            type="button"
            className={cn(
              "h-7 w-7 rounded-full border border-background shadow-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring",
              color === item.value ? "ring-2 ring-primary" : "ring-1 ring-border",
            )}
            style={{ backgroundColor: item.value }}
            onClick={() => onChange(item.value)}
            title={item.name}
          >
            <span className="sr-only">{item.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function createDraft(field: LabelField | null): FieldDraft {
  if (field === null) {
    return {
      key: "",
      label: "",
      type: "single_select",
      options: [createOptionDraft()],
    };
  }

  if (field.type === "text") {
    return {
      key: field.key,
      label: field.label,
      type: field.type,
      options: [],
    };
  }

  return {
    key: field.key,
    label: field.label,
    type: field.type,
    options: (field.options ?? []).map((option) => ({
      id: createDraftId(),
      value: option.value,
      label: option.label,
      color: option.color ?? null,
    })),
  };
}

function createOptionDraft(): OptionDraft {
  return {
    id: createDraftId(),
    value: "",
    label: "",
    color: null,
  };
}

function createDraftId(): string {
  return Math.random().toString(36).slice(2);
}

function isLabelFieldType(value: string): value is LabelFieldType {
  return value === "single_select" || value === "multi_select" || value === "text";
}

function validateDraft(
  draft: FieldDraft,
  existingKeys: string[],
  originalKey: string | null,
): FieldErrors {
  const errors: FieldErrors = {};
  const keyError = validateKey(draft.key, existingKeys, originalKey);
  if (keyError !== undefined) {
    errors.key = keyError;
  }
  if (draft.label.trim().length === 0) {
    errors.label = "显示名称 Label 必填";
  }
  if (draft.type !== "text") {
    if (draft.options.length === 0) {
      errors.options = "至少添加 1 个选项";
    } else {
      const seenValues = new Set<string>();
      for (const option of draft.options) {
        const value = option.value.trim();
        if (seenValues.has(value)) {
          errors.options = `选项值 Value 重复：${value}`;
          break;
        }
        seenValues.add(value);
      }
    }
  }
  return errors;
}

function validateKey(
  key: string,
  existingKeys: string[],
  originalKey: string | null,
): string | undefined {
  const normalizedKey = key.trim();
  if (normalizedKey.length === 0) {
    return "字段 Key 必填";
  }
  if (!KEY_PATTERN.test(normalizedKey)) {
    return "字段 Key 需匹配 ^[a-z][a-z0-9_]*$";
  }
  if (normalizedKey !== originalKey && existingKeys.includes(normalizedKey)) {
    return "字段 Key 已存在";
  }
  return undefined;
}

function buildField(draft: FieldDraft): LabelField {
  const key = draft.key.trim();
  const label = draft.label.trim();
  if (draft.type === "text") {
    return { key, label, type: "text" };
  }

  const options = draft.options.map(buildOption);
  if (draft.type === "single_select") {
    return { key, label, type: "single_select", options };
  }
  return { key, label, type: "multi_select", options };
}

function buildOption(option: OptionDraft): LabelOption {
  const base = {
    value: option.value.trim(),
    label: option.label.trim(),
  };
  if (option.color === null) {
    return base;
  }
  return { ...base, color: option.color };
}
