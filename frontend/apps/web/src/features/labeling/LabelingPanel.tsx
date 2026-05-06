import { useState } from "react";
import { Tags } from "lucide-react";

import { useLabelSchema } from "@/api/hooks/useLabelSchema";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { SchemaEditorDialog } from "@/features/labeling/SchemaEditorDialog";

type LabelingPanelProps = {
  open: boolean;
  queryId: number | null;
  onOpenChange: (open: boolean) => void;
};

export function LabelingPanel({ open, queryId, onOpenChange }: LabelingPanelProps) {
  const [schemaEditorOpen, setSchemaEditorOpen] = useState(false);
  const schema = useLabelSchema(open ? queryId : null);
  const fieldCount = schema.data?.fields.length ?? 0;

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="flex w-full flex-col gap-4 sm:max-w-md">
          <SheetHeader>
            <SheetTitle>打标</SheetTitle>
          </SheetHeader>

          <div className="space-y-4">
            <Button
              className="w-full gap-2"
              onClick={() => setSchemaEditorOpen(true)}
              disabled={queryId === null}
            >
              <Tags className="h-4 w-4" aria-hidden="true" />
              编辑打标 Schema
            </Button>

            <div className="rounded-md border bg-muted/30 p-3 text-sm">
              <div className="font-medium">Schema</div>
              <div className="mt-1 text-muted-foreground">
                {schema.isLoading ? "加载中..." : `${fieldCount} 个字段`}
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      <SchemaEditorDialog
        open={schemaEditorOpen}
        queryId={queryId}
        onOpenChange={setSchemaEditorOpen}
      />
    </>
  );
}
