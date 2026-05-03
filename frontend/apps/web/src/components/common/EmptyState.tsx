import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type EmptyStateProps = {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
};

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex min-h-[220px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed bg-background px-4 py-12 text-center",
        className,
      )}
    >
      {icon !== undefined ? (
        <div className="flex h-12 w-12 items-center justify-center rounded-lg border bg-muted/50 text-muted-foreground">
          {icon}
        </div>
      ) : null}
      <div className="max-w-md space-y-1">
        <div className="text-base font-medium">{title}</div>
        {description !== undefined ? (
          <div className="text-sm leading-6 text-muted-foreground">{description}</div>
        ) : null}
      </div>
      {action !== undefined ? <div className="pt-1">{action}</div> : null}
    </div>
  );
}
