import { useMemo, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";

import type { Annotation, AnnotationColor } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ANNOTATION_COLORS } from "@/components/annotation/colors";
import type { AnnotationIndex } from "@/components/annotation/useAnnotationIndex";
import { useDeleteAnnotation } from "@/hooks/useAnnotations";
import { formatApiError } from "@/lib/formatApiError";
import { cn } from "@/lib/utils";

interface AnnotationDrawerProps {
  open: boolean;
  queryId: number;
  annotationIndex: AnnotationIndex;
  onOpenChange: (open: boolean) => void;
}

type StatusFilter = "all" | "stale" | "orphan" | "current";

const ALL_VALUE = "__all";

export function AnnotationDrawer({
  open,
  queryId,
  annotationIndex,
  onOpenChange,
}: AnnotationDrawerProps) {
  const [authorFilter, setAuthorFilter] = useState(ALL_VALUE);
  const [colorFilter, setColorFilter] = useState<AnnotationColor | typeof ALL_VALUE>(ALL_VALUE);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [setFilter, setSetFilter] = useState(ALL_VALUE);
  const deleteAnnotation = useDeleteAnnotation(queryId);
  const staleIds = useMemo(
    () => new Set(annotationIndex.getStaleAnnotations().map((annotation) => annotation.id)),
    [annotationIndex],
  );
  const orphanIds = useMemo(
    () => new Set(annotationIndex.getOrphanAnnotations().map((annotation) => annotation.id)),
    [annotationIndex],
  );
  const authorOptions = useMemo(
    () => Array.from(new Set(annotationIndex.annotations.map((item) => item.author))).sort(),
    [annotationIndex.annotations],
  );
  const annotationSetOptions = useMemo(
    () =>
      Array.from(
        new Set(
          annotationIndex.annotations
            .map((item) => item.annotation_set)
            .filter((value): value is string => value !== null && value.length > 0),
        ),
      ).sort(),
    [annotationIndex.annotations],
  );
  const visibleAnnotations = useMemo(
    () =>
      annotationIndex.annotations.filter((annotation) => {
        if (authorFilter !== ALL_VALUE && annotation.author !== authorFilter) {
          return false;
        }
        if (colorFilter !== ALL_VALUE && annotation.color !== colorFilter) {
          return false;
        }
        if (setFilter !== ALL_VALUE && annotation.annotation_set !== setFilter) {
          return false;
        }
        if (statusFilter === "stale") {
          return staleIds.has(annotation.id);
        }
        if (statusFilter === "orphan") {
          return orphanIds.has(annotation.id);
        }
        if (statusFilter === "current") {
          return !staleIds.has(annotation.id) && !orphanIds.has(annotation.id);
        }
        return true;
      }),
    [
      annotationIndex.annotations,
      authorFilter,
      colorFilter,
      orphanIds,
      setFilter,
      staleIds,
      statusFilter,
    ],
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-[calc(100vw-2rem)] flex-col p-0 sm:max-w-2xl">
        <SheetHeader className="border-b px-5 py-4">
          <SheetTitle>Annotations</SheetTitle>
          <SheetDescription>
            {visibleAnnotations.length}/{annotationIndex.totalCount} annotations shown
          </SheetDescription>
        </SheetHeader>
        <div className="grid gap-2 border-b px-5 py-3 sm:grid-cols-4">
          <Select value={authorFilter} onValueChange={setAuthorFilter}>
            <SelectTrigger>
              <SelectValue placeholder="Author" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_VALUE}>All authors</SelectItem>
              {authorOptions.map((author) => (
                <SelectItem key={author} value={author}>
                  {author}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={colorFilter}
            onValueChange={(value) =>
              setColorFilter(value === ALL_VALUE ? ALL_VALUE : (value as AnnotationColor))
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="Color" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_VALUE}>All colors</SelectItem>
              {(["red", "yellow", "green", "blue", "gray"] as const).map((color) => (
                <SelectItem key={color} value={color}>
                  {color}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={statusFilter}
            onValueChange={(value) => setStatusFilter(value as StatusFilter)}
          >
            <SelectTrigger>
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All status</SelectItem>
              <SelectItem value="current">Current</SelectItem>
              <SelectItem value="stale">Stale</SelectItem>
              <SelectItem value="orphan">Orphan</SelectItem>
            </SelectContent>
          </Select>
          <Select value={setFilter} onValueChange={setSetFilter}>
            <SelectTrigger>
              <SelectValue placeholder="Set" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_VALUE}>All sets</SelectItem>
              {annotationSetOptions.map((annotationSet) => (
                <SelectItem key={annotationSet} value={annotationSet}>
                  {annotationSet}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {visibleAnnotations.length === 0 ? (
            <div className="px-5 py-8 text-sm text-muted-foreground">
              No annotations match the current filters.
            </div>
          ) : (
            <div className="divide-y">
              {visibleAnnotations.map((annotation) => (
                <AnnotationDrawerItem
                  key={annotation.id}
                  annotation={annotation}
                  stale={staleIds.has(annotation.id)}
                  orphan={orphanIds.has(annotation.id)}
                  deletePending={deleteAnnotation.isPending}
                  onDelete={() =>
                    deleteAnnotation.mutate(annotation.id, {
                      onError: (error) => toast.error(formatApiError(error)),
                    })
                  }
                />
              ))}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function AnnotationDrawerItem({
  annotation,
  stale,
  orphan,
  deletePending,
  onDelete,
}: {
  annotation: Annotation;
  stale: boolean;
  orphan: boolean;
  deletePending: boolean;
  onDelete: () => void;
}) {
  return (
    <div className="space-y-2 px-5 py-4">
      <div className="flex items-start gap-2">
        <span
          className={cn(
            "mt-1 h-2.5 w-2.5 shrink-0 rounded-full",
            ANNOTATION_COLORS[annotation.color].dot,
          )}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <div className="line-clamp-2 text-sm font-medium">
            {annotation.title ?? annotation.text ?? "Untitled annotation"}
          </div>
          <div className="mt-1 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
            <span className="truncate">author: {annotation.author}</span>
            <span className="truncate">
              row: {truncateMiddle(annotation.row_identity, 34)}
            </span>
            <span className="truncate">column: {annotation.column_key ?? "row"}</span>
            <span className="truncate">severity: {annotation.severity ?? "none"}</span>
            <span className="truncate">set: {annotation.annotation_set ?? "none"}</span>
            <span>{formatRelativeTime(annotation.created_at)}</span>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
          disabled={deletePending}
          aria-label="Delete annotation"
          onClick={onDelete}
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
        {stale ? <Badge variant="muted">Created on previous result</Badge> : null}
        {orphan ? <Badge variant="muted">Row not in current result</Badge> : null}
      </div>
    </div>
  );
}

function truncateMiddle(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  const edgeLength = Math.floor((maxLength - 1) / 2);
  return `${value.slice(0, edgeLength)}...${value.slice(value.length - edgeLength)}`;
}

function formatRelativeTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return formatDistanceToNow(date, { addSuffix: true });
}
