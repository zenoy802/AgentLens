import { AlertTriangle } from "lucide-react";
import { toast } from "sonner";

import { useDeleteConnection } from "@/api/hooks/useConnections";
import type { ConnectionRead } from "@/api/hooks/useConnections";
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

type DeleteConnectionDialogProps = {
  open: boolean;
  connection: ConnectionRead | null;
  onOpenChange: (open: boolean) => void;
};

export function DeleteConnectionDialog({
  open,
  connection,
  onOpenChange,
}: DeleteConnectionDialogProps) {
  const deleteConnection = useDeleteConnection();

  if (connection === null) {
    return null;
  }

  async function handleDelete() {
    if (connection === null) return;

    try {
      await deleteConnection.mutateAsync(connection.id);
      toast.success("连接已删除");
      onOpenChange(false);
    } catch (err) {
      toast.error(formatApiError(err));
    }
  }

  return (
    <Dialog open={open && connection !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-destructive" aria-hidden="true" />
            <DialogTitle>删除连接</DialogTitle>
          </div>
          <DialogDescription>
            此操作将级联删除关联的所有查询和分析数据
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 text-sm text-muted-foreground">
          <p>
            确认删除连接{" "}
            <span className="font-medium text-foreground">{connection.name}</span>？
          </p>
          <p>
            该连接下的所有命名查询、视图配置、打标记录和分析结果都将被级联删除。
            此操作不可撤销，建议先确认是否有关联数据。
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={() => void handleDelete()}
            disabled={deleteConnection.isPending}
          >
            删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
