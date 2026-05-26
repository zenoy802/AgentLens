import { memo, useState, type ReactNode } from "react";
import { formatDistanceToNow } from "date-fns";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";

import type { Annotation } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { ANNOTATION_COLORS } from "@/components/annotation/colors";
import { useDeleteAnnotation } from "@/hooks/useAnnotations";
import { formatApiError } from "@/lib/formatApiError";
import { cn } from "@/lib/utils";

interface AnnotationPopoverProps {
  queryId: number;
  annotations: Annotation[];
  staleAnnotationIds: ReadonlySet<number>;
  orphanAnnotationIds: ReadonlySet<number>;
  unknownColumnAnnotationIds: ReadonlySet<number>;
  children: ReactNode;
}

function AnnotationPopoverComponent({
  queryId,
  annotations,
  staleAnnotationIds,
  orphanAnnotationIds,
  unknownColumnAnnotationIds,
  children,
}: AnnotationPopoverProps) {
  const [open, setOpen] = useState(false);
  const deleteAnnotation = useDeleteAnnotation(queryId);

  if (annotations.length === 0) {
    return <>{children}</>;
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        align="start"
        className="max-h-96 w-96 overflow-y-auto p-0"
        onClick={(event) => event.stopPropagation()}
      >
        {open ? (
          <>
            <div className="border-b px-3 py-2 text-sm font-medium">
              {annotations.length} annotation{annotations.length === 1 ? "" : "s"}
            </div>
            <div className="divide-y">
              {annotations.map((annotation) => (
                <div key={annotation.id} className="space-y-2 px-3 py-3">
                  <div className="flex items-start gap-2">
                    <span
                      className={cn(
                        "mt-1 h-2.5 w-2.5 shrink-0 rounded-full",
                        ANNOTATION_COLORS[annotation.color].dot,
                      )}
                      aria-hidden="true"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">
                        {annotation.title ?? annotation.text ?? "Untitled annotation"}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                        <span>{annotation.author}</span>
                        {annotation.severity !== null ? <span>{annotation.severity}</span> : null}
                        {annotation.annotation_set !== null ? (
                          <span>{annotation.annotation_set}</span>
                        ) : null}
                        <span>{formatRelativeTime(annotation.created_at)}</span>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                      disabled={deleteAnnotation.isPending}
                      aria-label="Delete annotation"
                      onClick={(event) => {
                        event.stopPropagation();
                        deleteAnnotation.mutate(annotation.id, {
                          onError: (error) => toast.error(formatApiError(error)),
                        });
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                  {annotation.text !== null && annotation.text.length > 0 ? (
                    <div className="whitespace-pre-wrap break-words text-sm text-foreground">
                      {annotation.text}
                    </div>
                  ) : null}
                  <div className="flex flex-wrap gap-1.5">
                    {staleAnnotationIds.has(annotation.id) ? (
                      <Badge variant="muted">Created on previous result</Badge>
                    ) : null}
                    {orphanAnnotationIds.has(annotation.id) ? (
                      <Badge variant="muted">Row not in current result</Badge>
                    ) : null}
                    {unknownColumnAnnotationIds.has(annotation.id) ? (
                      <Badge variant="muted">Unknown column</Badge>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}

export const AnnotationPopover = memo(
  AnnotationPopoverComponent,
  (prev, next) =>
    prev.queryId === next.queryId &&
    prev.annotations === next.annotations &&
    prev.staleAnnotationIds === next.staleAnnotationIds &&
    prev.orphanAnnotationIds === next.orphanAnnotationIds &&
    prev.unknownColumnAnnotationIds === next.unknownColumnAnnotationIds &&
    prev.children === next.children,
);

function formatRelativeTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return formatDistanceToNow(date, { addSuffix: true });
}
