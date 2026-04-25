import { useRef, useState } from "react";
import { CheckCircle2, CircleDot, RotateCcw, Save } from "lucide-react";
import { toast } from "sonner";

import {
  useSaveViewConfig,
  useViewConfig,
  waitForPendingViewConfigSave,
} from "@/api/hooks/useViewConfig";
import { Button } from "@/components/ui/button";
import {
  getViewConfigPayloadFromState,
  useQueryStore,
  viewConfigPayloadMatchesState,
} from "@/stores/queryStore";

interface ViewConfigBarProps {
  queryId: number | null;
}

export function ViewConfigBar({ queryId }: ViewConfigBarProps) {
  const isDirty = useQueryStore((state) => state.isDirty);
  const applyViewConfig = useQueryStore((state) => state.applyViewConfig);
  const [isRestoring, setIsRestoring] = useState(false);
  const isRestoringRef = useRef(false);

  const { refetch } = useViewConfig(queryId);
  const saveViewConfig = useSaveViewConfig();

  const activeQueryId = queryId;
  if (activeQueryId === null) {
    return null;
  }
  const resolvedQueryId: number = activeQueryId;

  async function handleSave() {
    if (isRestoringRef.current) {
      return;
    }

    const payload = getViewConfigPayloadFromState(useQueryStore.getState());
    try {
      const saved = await saveViewConfig.mutateAsync({
        queryId: resolvedQueryId,
        payload,
      });
      const currentState = useQueryStore.getState();
      if (
        currentState.queryId === resolvedQueryId &&
        viewConfigPayloadMatchesState(payload, currentState)
      ) {
        applyViewConfig(saved);
        toast.success("视图已保存");
      } else {
        toast.success("视图已保存，本地还有未保存的变更");
      }
    } catch {
      // useSaveViewConfig already reports API errors.
    }
  }

  async function handleRestore() {
    if (saveViewConfig.isPending || isRestoringRef.current) {
      return;
    }

    isRestoringRef.current = true;
    setIsRestoring(true);
    const snapshot = getViewConfigPayloadFromState(useQueryStore.getState());
    try {
      await waitForPendingViewConfigSave(resolvedQueryId);
      const result = await refetch();
      const currentState = useQueryStore.getState();
      if (
        result.data !== undefined &&
        currentState.queryId === resolvedQueryId &&
        viewConfigPayloadMatchesState(snapshot, currentState)
      ) {
        applyViewConfig(result.data);
        toast.success("视图已恢复");
      }
    } finally {
      isRestoringRef.current = false;
      setIsRestoring(false);
    }
  }

  return (
    <div className="flex h-9 items-center justify-between border-b bg-muted/30 px-3 text-sm">
      <div className="flex items-center gap-2 text-muted-foreground">
        {isDirty ? (
          <>
            <CircleDot className="h-3.5 w-3.5 text-amber-500" aria-hidden="true" />
            <span>有未保存的视图变更</span>
          </>
        ) : (
          <>
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" aria-hidden="true" />
            <span>视图已保存</span>
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          disabled={!isDirty || saveViewConfig.isPending || isRestoring}
          onClick={() => void handleRestore()}
          title="放弃未保存的变更，重新从服务端加载"
        >
          <RotateCcw className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
          {isRestoring ? "恢复中..." : "恢复"}
        </Button>
        <Button
          size="sm"
          disabled={!isDirty || saveViewConfig.isPending || isRestoring}
          onClick={() => void handleSave()}
        >
          <Save className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
          {saveViewConfig.isPending ? "保存中..." : "保存视图"}
        </Button>
      </div>
    </div>
  );
}
