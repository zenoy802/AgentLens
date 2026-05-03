import { FormEvent, useEffect, useState } from "react";
import { Edit, Save } from "lucide-react";
import { toast } from "sonner";

import type { NamedQueryRead } from "@/api/hooks/useQueries";
import { usePromoteQuery, useUpdateQuery } from "@/api/hooks/useQueries";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatApiError, getApiError } from "@/lib/formatApiError";
import { cn } from "@/lib/utils";

export type PromotableQuery = Pick<
  NamedQueryRead,
  "id" | "name" | "description" | "expires_at" | "is_named"
>;

type PromoteQueryDialogProps = {
  open: boolean;
  query: PromotableQuery | null;
  onOpenChange: (open: boolean) => void;
  onPromoted?: (query: NamedQueryRead) => void;
  onSaved?: (query: NamedQueryRead) => void;
};

export function PromoteQueryDialog({
  open,
  query,
  onOpenChange,
  onPromoted,
  onSaved,
}: PromoteQueryDialogProps) {
  const promoteQuery = usePromoteQuery();
  const updateQuery = useUpdateQuery();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [expiresAt, setExpiresAt] = useState(defaultExpirationDate());
  const [neverExpires, setNeverExpires] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    const queryExpiresAt = query?.expires_at ?? null;
    setName(query?.name ?? "");
    setDescription(query?.description ?? "");
    setNeverExpires(query?.is_named === true && queryExpiresAt === null);
    setExpiresAt(dateInputValue(queryExpiresAt) ?? defaultExpirationDate());
    setFormError(null);
  }, [open, query]);

  if (query === null) {
    return null;
  }

  const isEditMode = query.is_named;
  const isPending = promoteQuery.isPending || updateQuery.isPending;
  const today = todayInputValue();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (query === null) {
      return;
    }

    const trimmedName = name.trim();
    if (trimmedName.length === 0) {
      setFormError("名称不能为空。");
      return;
    }
    if (!neverExpires && expiresAt.length === 0) {
      setFormError("请选择过期日期，或勾选永不过期。");
      return;
    }
    if (!neverExpires && expiresAt < todayInputValue()) {
      setFormError("过期日期不能早于今天。");
      return;
    }

    const payload = {
      name: trimmedName,
      description: description.trim() || null,
      expires_at: neverExpires ? null : serializeExpirationDate(expiresAt),
    };

    try {
      const savedQuery = isEditMode
        ? await updateQuery.mutateAsync({ id: query.id, payload })
        : await promoteQuery.mutateAsync({ id: query.id, payload });
      onSaved?.(savedQuery);
      if (!isEditMode) {
        onPromoted?.(savedQuery);
      }
      toast.success(isEditMode ? "查询已更新" : "查询已保存");
      onOpenChange(false);
    } catch (error) {
      const apiError = getApiError(error);
      const message =
        apiError?.error.code === "QUERY_NAME_CONFLICT"
          ? "同一连接下已存在同名查询，请换一个名称。"
          : formatApiError(error);
      setFormError(message);
      toast.error(message);
    }
  }

  return (
    <Dialog open={open && query !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2">
            {isEditMode ? (
              <Edit className="h-5 w-5" aria-hidden="true" />
            ) : (
              <Save className="h-5 w-5" aria-hidden="true" />
            )}
            <DialogTitle>{isEditMode ? "编辑查询" : "Promote 查询"}</DialogTitle>
          </div>
          <DialogDescription>
            {isEditMode ? "修改命名查询信息" : "将临时查询保存为命名查询"}
          </DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={(event) => void handleSubmit(event)}>
          <label className="block text-sm font-medium">
            名称 <span className="text-destructive">*</span>
            <input
              className={cn(
                "mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring",
                formError !== null && "border-destructive focus:ring-destructive",
              )}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setFormError(null);
              }}
              required
              maxLength={200}
            />
          </label>

          <label className="block text-sm font-medium">
            描述
            <textarea
              className="mt-1 min-h-24 w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <label className="block text-sm font-medium">
              过期日期
              <input
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
                type="date"
                min={today}
                value={expiresAt}
                disabled={neverExpires}
                onChange={(event) => {
                  setExpiresAt(event.target.value);
                  setFormError(null);
                }}
              />
            </label>
            <label className="flex h-9 items-center gap-2 text-sm font-medium">
              <input
                className="h-4 w-4 rounded border-input"
                type="checkbox"
                checked={neverExpires}
                onChange={(event) => {
                  const checked = event.target.checked;
                  setNeverExpires(checked);
                  if (!checked && expiresAt.length === 0) {
                    setExpiresAt(defaultExpirationDate());
                  }
                  setFormError(null);
                }}
              />
              永不过期
            </label>
          </div>

          {formError !== null ? (
            <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {formError}
            </p>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit" disabled={isPending || name.trim().length === 0}>
              {isEditMode ? "保存" : "Promote"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function defaultExpirationDate(): string {
  const date = new Date();
  date.setDate(date.getDate() + 90);
  return toInputDate(date);
}

function todayInputValue(): string {
  return toInputDate(new Date());
}

function dateInputValue(value: string | null): string | null {
  if (value === null) {
    return null;
  }

  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return toInputDate(date);
}

function toInputDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function serializeExpirationDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day, 23, 59, 59, 999).toISOString();
}
