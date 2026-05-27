import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import type { QueryFingerprints } from "@/api/types";
import { AddAnnotationDialog } from "@/components/annotation/AddAnnotationDialog";
import { AnnotationDrawer } from "@/components/annotation/AnnotationDrawer";
import type { AnnotationIndex } from "@/components/annotation/useAnnotationIndex";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AnnotationStreamStatus } from "@/hooks/useAnnotationStream";
import { useClearAnnotations } from "@/hooks/useAnnotations";
import { formatApiError } from "@/lib/formatApiError";
import { markAnnotationsSeen } from "@/lib/onboarding";
import { cn } from "@/lib/utils";
import { useQueryStore } from "@/stores/queryStore";

interface AnnotationBannerProps {
  queryId: number | null;
  annotationIndex: AnnotationIndex;
  streamStatus: AnnotationStreamStatus;
  fingerprints?: QueryFingerprints | null;
  view: "row" | "trajectory";
  onRetryStream: () => void;
  onSwitchToRowView: () => void;
}

export function AnnotationBanner({
  queryId,
  annotationIndex,
  streamStatus,
  fingerprints,
  view,
  onRetryStream,
  onSwitchToRowView,
}: AnnotationBannerProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const selectedRowIds = useQueryStore((state) => state.selectedRowIds);
  const clearAnnotations = useClearAnnotations(queryId ?? 0);
  const selectedRowIdentity = useMemo(() => {
    if (selectedRowIds.size !== 1) {
      return null;
    }
    return Array.from(selectedRowIds)[0] ?? null;
  }, [selectedRowIds]);

  useEffect(() => {
    if (annotationIndex.totalCount > 0) {
      markAnnotationsSeen();
    }
  }, [annotationIndex.totalCount]);

  if (queryId === null) {
    return null;
  }

  function handleClearAgents() {
    if (
      !window.confirm(
        "Clear all agent annotations for this query? Human annotations will remain.",
      )
    ) {
      return;
    }

    clearAnnotations.mutate(
      { author_prefix: "agent:" },
      {
        onSuccess: (result) => toast.success(`Cleared ${result.deleted} annotations`),
        onError: (error) => toast.error(formatApiError(error)),
      },
    );
  }

  return (
    <div className="border-t bg-background px-4 py-3">
      <div className="flex flex-col gap-3 rounded-md border bg-muted/30 px-3 py-3 text-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">
              {annotationIndex.totalCount === 0
                ? "No annotations yet."
                : `This query has ${annotationIndex.totalCount} annotations.`}
            </span>
            <StreamStatusBadge status={streamStatus} onRetry={onRetryStream} />
          </div>
          {annotationIndex.totalCount === 0 ? (
            <div className="text-muted-foreground">
              Agent and human annotations will appear here.
            </div>
          ) : view === "trajectory" ? (
            <div className="text-muted-foreground">
              Switch to Row view to see them.
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(annotationIndex.byAuthor).map(([author, count]) => (
                <Badge key={author} variant="outline">
                  {author} ({count})
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {view === "trajectory" ? (
            <Button variant="outline" size="sm" onClick={onSwitchToRowView}>
              Switch to Row view
            </Button>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={() => setDrawerOpen(true)}>
                View all
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={clearAnnotations.isPending}
                onClick={handleClearAgents}
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                Clear agents
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => setAddDialogOpen(true)}
              >
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                Add annotation
              </Button>
            </>
          )}
        </div>
      </div>

      <AnnotationDrawer
        open={drawerOpen}
        queryId={queryId}
        annotationIndex={annotationIndex}
        onOpenChange={setDrawerOpen}
      />
      <AddAnnotationDialog
        open={addDialogOpen}
        queryId={queryId}
        rowIdentity={selectedRowIdentity}
        fingerprints={fingerprints}
        onOpenChange={setAddDialogOpen}
      />
    </div>
  );
}

function StreamStatusBadge({
  status,
  onRetry,
}: {
  status: AnnotationStreamStatus;
  onRetry: () => void;
}) {
  const dotClass =
    status === "connected"
      ? "bg-green-500"
      : status === "reconnecting" || status === "connecting"
        ? "bg-yellow-500"
        : "bg-red-500";

  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={cn("h-2 w-2 rounded-full", dotClass)} aria-hidden="true" />
      {status}
      {status === "disconnected" || status === "error" ? (
        <button
          type="button"
          className="inline-flex items-center gap-1 font-medium text-foreground hover:text-primary"
          onClick={onRetry}
        >
          <RefreshCw className="h-3 w-3" aria-hidden="true" />
          retry
        </button>
      ) : null}
    </span>
  );
}
