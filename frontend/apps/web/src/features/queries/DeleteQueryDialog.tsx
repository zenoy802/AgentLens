import { AlertTriangle, X } from "lucide-react";
import { toast } from "sonner";

import type { NamedQueryRead } from "@/api/hooks/useQueries";
import { useDeleteQuery } from "@/api/hooks/useQueries";
import { Button } from "@/components/ui/button";
import { formatApiError } from "@/lib/formatApiError";

type DeleteQueryDialogProps = {
  open: boolean;
  query: NamedQueryRead | null;
  onOpenChange: (open: boolean) => void;
};

export function DeleteQueryDialog({ open, query, onOpenChange }: DeleteQueryDialogProps) {
  const deleteQuery = useDeleteQuery();

  if (!open || query === null) {
    return null;
  }

  const displayName = query.name ?? "（临时）";

  async function handleDelete() {
    if (query === null) {
      return;
    }

    try {
      await deleteQuery.mutateAsync(query.id);
      toast.success("查询已删除");
      onOpenChange(false);
    } catch (error) {
      toast.error(formatApiError(error));
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-query-title"
        className="w-full max-w-md rounded-lg border bg-background p-5 shadow-lg"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" aria-hidden="true" />
            <h2 id="delete-query-title" className="text-base font-semibold">
              删除查询
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

        <div className="mt-4 space-y-2 text-sm text-muted-foreground">
          <p>
            确认删除 <span className="font-medium text-foreground">{displayName}</span>？
          </p>
          <p>将删除关联的打标和分析。</p>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={() => void handleDelete()}
            disabled={deleteQuery.isPending}
          >
            删除
          </Button>
        </div>
      </div>
    </div>
  );
}
