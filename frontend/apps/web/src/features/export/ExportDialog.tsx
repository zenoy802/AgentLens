import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";

import type { ExportRequest } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { getApiError } from "@/lib/formatApiError";
import { downloadBlob, parseFilenameFromHeader } from "@/lib/download";

type ExportFormat = ExportRequest["format"];

type ExportDialogProps = {
  open: boolean;
  queryId: number | null;
  onBeforeExport?: () => boolean | Promise<boolean>;
  onOpenChange: (open: boolean) => void;
};

export function ExportDialog({
  open,
  queryId,
  onBeforeExport,
  onOpenChange,
}: ExportDialogProps) {
  const [format, setFormat] = useState<ExportFormat>("csv");
  const [includeLabels, setIncludeLabels] = useState(true);
  const [isExporting, setIsExporting] = useState(false);

  async function handleSubmit() {
    if (queryId === null || isExporting) {
      return;
    }

    const payload: ExportRequest = {
      format,
      include_labels: includeLabels,
      json_serialization: "string",
    };
    const toastId = toast.loading("正在导出...");
    setIsExporting(true);

    try {
      const canExport = onBeforeExport === undefined ? true : await onBeforeExport();
      if (!canExport) {
        toast.dismiss(toastId);
        return;
      }

      const response = await fetch(`/api/v1/queries/${queryId}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        toast.error(await getExportErrorMessage(response), { id: toastId });
        return;
      }

      const blob = await response.blob();
      const filename = parseFilenameFromHeader(
        response.headers.get("Content-Disposition"),
        `query.${format}`,
      );
      downloadBlob(blob, filename);
      toast.success("导出完成", { id: toastId });
      onOpenChange(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : "导出失败";
      toast.error(message, { id: toastId });
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !isExporting && onOpenChange(nextOpen)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>导出查询结果</DialogTitle>
          <DialogDescription>重新执行当前查询，并按视图配置导出结果。</DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-1">
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">Format</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <RadioOption
                checked={format === "csv"}
                disabled={isExporting}
                label="CSV"
                name="export-format"
                onChange={() => setFormat("csv")}
              />
              <RadioOption
                checked={format === "xlsx"}
                disabled={isExporting}
                label="Excel (.xlsx)"
                name="export-format"
                onChange={() => setFormat("xlsx")}
              />
            </div>
          </fieldset>

          <Label className="flex items-center gap-2 rounded-md border p-3">
            <input
              className="h-4 w-4 rounded border-input"
              type="checkbox"
              checked={includeLabels}
              disabled={isExporting}
              onChange={(event) => setIncludeLabels(event.target.checked)}
            />
            包含打标数据
          </Label>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">JSON 字段</legend>
            <RadioOption
              checked
              disabled={isExporting}
              label="原样 JSON 字符串"
              name="json-serialization"
              onChange={() => undefined}
            />
          </fieldset>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isExporting}>
            取消
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={queryId === null || isExporting}>
            {isExporting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Download className="mr-2 h-4 w-4" aria-hidden="true" />
            )}
            导出
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type RadioOptionProps = {
  checked: boolean;
  disabled: boolean;
  label: string;
  name: string;
  onChange: () => void;
};

function RadioOption({ checked, disabled, label, name, onChange }: RadioOptionProps) {
  return (
    <Label className="flex items-center gap-2 rounded-md border p-3">
      <input
        className="h-4 w-4 border-input"
        type="radio"
        name={name}
        checked={checked}
        disabled={disabled}
        onChange={onChange}
      />
      {label}
    </Label>
  );
}

async function getExportErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as unknown;
    const apiError = getApiError(body);
    return apiError?.error.message ?? `导出失败 (${response.status})`;
  } catch {
    return `导出失败 (${response.status})`;
  }
}
