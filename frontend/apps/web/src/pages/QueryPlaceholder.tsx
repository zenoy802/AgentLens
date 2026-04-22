import { ArrowLeft, Terminal } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type QueryPlaceholderProps = {
  mode: "new" | "detail";
};

export function QueryPlaceholder({ mode }: QueryPlaceholderProps) {
  const { queryId } = useParams();
  const title = mode === "new" ? "新建查询" : `查询 #${queryId ?? ""}`;
  const curlCommand =
    mode === "new" ? createTemporaryQueryCurl : executeExistingQueryCurl(queryId ?? "1");

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            完整 Query 编辑与详情页会在下一阶段实现；当前阶段先通过后端 API 创建或执行查询。
          </p>
        </div>
        <Link to="/queries" className={cn(buttonVariants({ variant: "outline" }), "gap-2")}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          返回列表
        </Link>
      </div>

      <div className="rounded-lg border bg-card p-5">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Terminal className="h-4 w-4" aria-hidden="true" />
          API 验收入口
        </div>
        <pre className="mt-4 overflow-x-auto rounded-md bg-muted p-4 text-xs leading-6 text-muted-foreground">
          {curlCommand}
        </pre>
        <div className="mt-4">
          <Button variant="outline" onClick={() => void navigator.clipboard.writeText(curlCommand)}>
            复制命令
          </Button>
        </div>
      </div>
    </div>
  );
}

const createTemporaryQueryCurl = `curl -sS -X POST "http://127.0.0.1:8000/api/v1/execute" \\
  -H "Content-Type: application/json" \\
  -d '{
    "connection_id": 1,
    "sql": "SELECT 1 AS n",
    "save_as_temporary": true
  }'`;

function executeExistingQueryCurl(queryId: string): string {
  return `curl -sS -X POST "http://127.0.0.1:8000/api/v1/queries/${queryId}/execute" \\
  -H "Content-Type: application/json" \\
  -d '{
    "row_limit": 100
  }'`;
}
