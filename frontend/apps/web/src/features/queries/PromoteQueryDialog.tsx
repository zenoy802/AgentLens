import { FormEvent, useEffect, useState } from "react";
import { Save, X } from "lucide-react";
import { toast } from "sonner";

import type { NamedQueryRead } from "@/api/hooks/useQueries";
import { usePromoteQuery } from "@/api/hooks/useQueries";
import { Button } from "@/components/ui/button";

type PromoteQueryDialogProps = {
  open: boolean;
  query: NamedQueryRead | null;
  onOpenChange: (open: boolean) => void;
};

export function PromoteQueryDialog({ open, query, onOpenChange }: PromoteQueryDialogProps) {
  const promoteQuery = usePromoteQuery();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [expiresAt, setExpiresAt] = useState(defaultExpirationDate());

  useEffect(() => {
    if (!open) {
      return;
    }
    setName(query?.name ?? "");
    setDescription(query?.description ?? "");
    setExpiresAt(defaultExpirationDate());
  }, [open, query]);

  if (!open || query === null) {
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (query === null) {
      return;
    }

    try {
      await promoteQuery.mutateAsync({
        id: query.id,
        payload: {
          name: name.trim(),
          description: description.trim() || null,
          expires_at: expiresAt ? `${expiresAt}T00:00:00.000Z` : null,
        },
      });
      toast.success("查询已保存");
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存查询失败");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="promote-query-title"
        className="w-full max-w-lg rounded-lg border bg-background p-5 shadow-lg"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2">
            <Save className="h-5 w-5" aria-hidden="true" />
            <h2 id="promote-query-title" className="text-base font-semibold">
              保存临时查询
            </h2>
          </div>
          <button
            type="button"
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            onClick={() => onOpenChange(false)}
            aria-label="关闭"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <form className="mt-5 space-y-4" onSubmit={(event) => void handleSubmit(event)}>
          <label className="block text-sm font-medium">
            名称
            <input
              className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
              value={name}
              onChange={(event) => setName(event.target.value)}
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

          <label className="block text-sm font-medium">
            过期日期
            <input
              className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
              type="date"
              value={expiresAt}
              onChange={(event) => setExpiresAt(event.target.value)}
            />
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit" disabled={promoteQuery.isPending || name.trim().length === 0}>
              保存
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function defaultExpirationDate(): string {
  const date = new Date();
  date.setDate(date.getDate() + 90);
  return date.toISOString().slice(0, 10);
}
