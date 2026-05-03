import { AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import type { NamedQueryRead } from "@/api/hooks/useQueries";
import { useDeleteQuery } from "@/api/hooks/useQueries";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatApiError } from "@/lib/formatApiError";

type DeleteQueryDialogProps = {
  open: boolean;
  query: NamedQueryRead | null;
  onOpenChange: (open: boolean) => void;
};

export function DeleteQueryDialog({ open, query, onOpenChange }: DeleteQueryDialogProps) {
  const deleteQuery = useDeleteQuery();

  if (query === null) {
    return null;
  }

  const displayName = query.name ?? "（临时）";
  const labelRecordCount = query.label_record_count ?? 0;
  const llmAnalysisCount = query.llm_analysis_count ?? 0;

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
    <Dialog open={open && query !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" aria-hidden="true" />
            <DialogTitle>删除查询</DialogTitle>
          </div>
          <DialogDescription>此操作不可撤销。</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm text-muted-foreground">
          <p>
            即将删除查询{" "}
            <span className="font-medium text-foreground">{displayName}</span>
          </p>
          <div>
            <p>这将同时删除：</p>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>{labelRecordCount} 条打标</li>
              <li>{llmAnalysisCount} 条 LLM 分析记录</li>
              <li>视图配置</li>
            </ul>
          </div>
          <p className="font-medium text-destructive">此操作不可撤销。</p>
        </div>

        <DialogFooter>
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
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
