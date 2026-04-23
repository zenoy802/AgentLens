import { AlertCircle } from "lucide-react";

import { getApiError } from "@/lib/formatApiError";

type ErrorAlertProps = {
  error: unknown;
};

export function ErrorAlert({ error }: ErrorAlertProps) {
  const apiError = getApiError(error);
  const code = apiError?.error.code ?? "UNKNOWN_ERROR";
  const message =
    apiError?.error.message ??
    (error instanceof Error && error.message.length > 0 ? error.message : "未知错误");
  const detail = apiError?.error.detail;

  return (
    <div
      role="alert"
      className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0 space-y-2">
          <div className="font-medium">{code}</div>
          <div className="text-destructive/90">{message}</div>
          {detail !== undefined && detail !== null ? (
            <details className="text-xs text-destructive/80">
              <summary className="cursor-pointer select-none">查看 detail</summary>
              <pre className="mt-2 max-h-56 overflow-auto rounded-md bg-background/80 p-3 text-foreground">
                {formatDetail(detail)}
              </pre>
            </details>
          ) : null}
        </div>
      </div>
    </div>
  );
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
