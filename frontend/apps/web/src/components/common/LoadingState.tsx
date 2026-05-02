import { cn } from "@/lib/utils";

type LoadingStateProps = {
  label?: string;
  rows?: number;
  className?: string;
};

export function LoadingState({
  label = "正在加载...",
  rows = 4,
  className,
}: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn("rounded-lg border bg-background p-4", className)}
    >
      <div className="mb-4 text-sm text-muted-foreground">{label}</div>
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, index) => (
          <div key={index} className="flex animate-pulse items-center gap-3">
            <div className="h-4 w-4 rounded bg-muted" />
            <div className="h-4 flex-1 rounded bg-muted" />
            <div className="hidden h-4 w-28 rounded bg-muted sm:block" />
          </div>
        ))}
      </div>
    </div>
  );
}
