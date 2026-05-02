import type { ReactNode } from "react";
import { AlertCircle } from "lucide-react";

import { getApiError } from "@/lib/formatApiError";
import { cn } from "@/lib/utils";

type ErrorStateProps = {
  error: unknown;
  title?: string;
  action?: ReactNode;
  className?: string;
};

export function ErrorState({ error, title = "操作失败", action, className }: ErrorStateProps) {
  const parsed = parseError(error);

  return (
    <div
      role="alert"
      className={cn(
        "rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="font-medium">{title}</div>
          <div className="break-words text-destructive/90">
            {parsed.code}: {parsed.message}
          </div>
          {parsed.detail !== undefined && parsed.detail !== null ? (
            <details className="text-xs text-destructive/80">
              <summary className="cursor-pointer select-none">查看 detail</summary>
              <pre className="mt-2 max-h-56 overflow-auto rounded-md bg-background/80 p-3 text-foreground">
                {formatDetail(parsed.detail)}
              </pre>
            </details>
          ) : null}
          {action !== undefined ? <div className="pt-1">{action}</div> : null}
        </div>
      </div>
    </div>
  );
}

function parseError(error: unknown): {
  code: string;
  message: string;
  detail: unknown;
} {
  const apiError = getApiError(error);
  if (apiError !== null) {
    return {
      code: apiError.error.code,
      message: apiError.error.message,
      detail: apiError.error.detail,
    };
  }

  return {
    code: "UNKNOWN_ERROR",
    message: error instanceof Error && error.message.length > 0 ? error.message : "未知错误",
    detail: undefined,
  };
}

function formatDetail(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }

  try {
    return JSON.stringify(detail, null, 2);
  } catch {
    return String(detail);
  }
}
