import React, { type ErrorInfo, type ReactNode } from "react";
import { Clipboard, Home, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  hasError: boolean;
  error: Error | null;
};

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    error: null,
  };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info);
  }

  render() {
    if (this.state.hasError) {
      return <ErrorFallback error={this.state.error} />;
    }

    return this.props.children;
  }
}

function ErrorFallback({ error }: { error: Error | null }) {
  const message = error?.message ?? "页面渲染失败";
  const errorInfo = error === null ? message : `${error.name}: ${error.message}\n${error.stack ?? ""}`;

  async function handleCopyError() {
    try {
      await navigator.clipboard.writeText(errorInfo);
      toast.success("错误信息已复制");
    } catch {
      window.prompt("复制错误信息", errorInfo);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <section className="w-full max-w-xl rounded-lg border bg-card p-6 shadow-sm">
        <div className="text-sm font-medium uppercase text-destructive">Render Error</div>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">页面发生错误</h1>
        <p className="mt-3 break-words text-sm text-muted-foreground">{message}</p>
        <div className="mt-5 flex flex-wrap gap-2">
          <Button type="button" className="gap-2" onClick={() => window.location.assign("/")}>
            <Home className="h-4 w-4" aria-hidden="true" />
            返回首页
          </Button>
          <Button
            type="button"
            variant="outline"
            className="gap-2"
            onClick={() => window.location.reload()}
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            刷新页面
          </Button>
          <Button type="button" variant="outline" className="gap-2" onClick={handleCopyError}>
            <Clipboard className="h-4 w-4" aria-hidden="true" />
            复制错误信息
          </Button>
        </div>
      </section>
    </main>
  );
}
