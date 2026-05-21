import { useEffect, useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import type {
  AnnotationColor,
  AnnotationSeverity,
  QueryFingerprints,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ANNOTATION_COLORS } from "@/components/annotation/colors";
import { useCreateAnnotation } from "@/hooks/useAnnotations";
import { formatApiError } from "@/lib/formatApiError";
import { cn } from "@/lib/utils";

interface AddAnnotationDialogProps {
  open: boolean;
  queryId: number;
  rowIdentity?: string | null;
  columnKey?: string | null;
  fingerprints?: QueryFingerprints | null;
  onOpenChange: (open: boolean) => void;
}

const NO_SEVERITY = "__none";

export function AddAnnotationDialog({
  open,
  queryId,
  rowIdentity,
  columnKey = null,
  fingerprints,
  onOpenChange,
}: AddAnnotationDialogProps) {
  const createAnnotation = useCreateAnnotation(queryId);
  const [editableRowIdentity, setEditableRowIdentity] = useState(rowIdentity ?? "");
  const [color, setColor] = useState<AnnotationColor>("yellow");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [severity, setSeverity] = useState<AnnotationSeverity | typeof NO_SEVERITY>(
    NO_SEVERITY,
  );
  const [annotationSet, setAnnotationSet] = useState("");
  const resolvedRowIdentity = rowIdentity ?? editableRowIdentity;
  const rowIdentityIsEditable = rowIdentity == null;
  const submitDisabled =
    resolvedRowIdentity.length === 0 ||
    title.length > 256 ||
    text.length > 2000 ||
    createAnnotation.isPending;

  useEffect(() => {
    if (open) {
      setEditableRowIdentity(rowIdentity ?? "");
    }
  }, [open, rowIdentity]);

  function resetForm() {
    setEditableRowIdentity(rowIdentity ?? "");
    setColor("yellow");
    setTitle("");
    setText("");
    setSeverity(NO_SEVERITY);
    setAnnotationSet("");
  }

  function handleSubmit() {
    if (submitDisabled) {
      return;
    }

    createAnnotation.mutate(
      {
        row_identity: resolvedRowIdentity,
        column_key: columnKey,
        author: "human",
        color,
        title: title.trim().length > 0 ? title.trim() : null,
        text: text.trim().length > 0 ? text.trim() : null,
        severity: severity === NO_SEVERITY ? null : severity,
        annotation_set:
          annotationSet.trim().length > 0 ? annotationSet.trim() : null,
        sql_fingerprint: fingerprints?.sql ?? null,
        schema_fingerprint: fingerprints?.schema ?? null,
        result_fingerprint: fingerprints?.result ?? null,
      },
      {
        onSuccess: () => {
          toast.success("Annotation added");
          resetForm();
          onOpenChange(false);
        },
        onError: (error) => toast.error(formatApiError(error)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Add annotation</DialogTitle>
          <DialogDescription>
            Author is fixed to human. The annotation will appear in Row view.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {rowIdentityIsEditable ? (
            <Field label="Row identity">
              <Input
                value={editableRowIdentity}
                maxLength={256}
                placeholder="_row_identity value"
                onChange={(event) => setEditableRowIdentity(event.target.value)}
              />
            </Field>
          ) : (
            <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              <div className="font-medium text-foreground">Row</div>
              <div className="mt-1 break-all">{rowIdentity}</div>
              <div className="mt-1">Column: {columnKey ?? "row annotation"}</div>
            </div>
          )}

          <Field label="Color">
            <div className="flex flex-wrap gap-2">
              {(["red", "yellow", "green", "blue", "gray"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  className={cn(
                    "flex h-8 items-center gap-2 rounded-md border px-2 text-xs font-medium",
                    color === item && "border-primary ring-1 ring-primary",
                  )}
                  aria-pressed={color === item}
                  onClick={() => setColor(item)}
                >
                  <span
                    className={cn(
                      "h-3 w-3 rounded-full",
                      ANNOTATION_COLORS[item].dot,
                    )}
                    aria-hidden="true"
                  />
                  {item}
                </button>
              ))}
            </div>
          </Field>

          <Field label="Title">
            <Input
              value={title}
              maxLength={256}
              placeholder="Optional title"
              onChange={(event) => setTitle(event.target.value)}
            />
          </Field>

          <Field label="Text">
            <textarea
              value={text}
              maxLength={2000}
              rows={5}
              className="min-h-28 w-full rounded-md border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              placeholder="Concise explanation"
              onChange={(event) => setText(event.target.value)}
            />
            <div className="mt-1 text-right text-xs text-muted-foreground">
              {text.length}/2000
            </div>
          </Field>

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Severity">
              <Select
                value={severity}
                onValueChange={(value) =>
                  setSeverity(
                    value === NO_SEVERITY ? NO_SEVERITY : (value as AnnotationSeverity),
                  )
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Severity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_SEVERITY}>None</SelectItem>
                  <SelectItem value="info">Info</SelectItem>
                  <SelectItem value="warning">Warning</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field label="Annotation set">
              <Input
                value={annotationSet}
                maxLength={128}
                placeholder="Optional"
                onChange={(event) => setAnnotationSet(event.target.value)}
              />
            </Field>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitDisabled}>
            {createAnnotation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
            ) : null}
            Add annotation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
    </label>
  );
}
