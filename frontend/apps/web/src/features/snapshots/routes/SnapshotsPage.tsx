import { useState } from "react";
import { Archive, RefreshCw, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import type { RunSnapshotRead } from "@/api/types";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  useCreateRunSnapshot,
  useRunSnapshot,
  useRunSnapshots,
} from "@/features/snapshots/api";
import { formatApiError } from "@/lib/formatApiError";
import { cn } from "@/lib/utils";

export function SnapshotsPage() {
  const snapshots = useRunSnapshots({ limit: 50 });
  const createSnapshot = useCreateRunSnapshot();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const items = snapshots.data?.items ?? [];

  async function retry(snapshot: RunSnapshotRead) {
    try {
      await createSnapshot.mutateAsync({
        name: `${snapshot.name}-retry`,
        connection_id: snapshot.connection_id,
        named_query_id: snapshot.named_query_id,
        trace_contract_id: snapshot.trace_contract_id,
        build_policy: snapshot.build_policy,
      });
      toast.success("Snapshot retry 已提交");
    } catch (error) {
      toast.error(formatApiError(error));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Run Snapshots</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          不可变、可校验的 trajectory 输入；building 状态仅在页面可见时轮询。
        </p>
      </div>

      {snapshots.isLoading ? (
        <LoadingState label="正在加载 snapshots…" rows={5} />
      ) : snapshots.isError ? (
        <ErrorState
          error={snapshots.error}
          action={
            <Button variant="outline" size="sm" onClick={() => void snapshots.refetch()}>
              重试
            </Button>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Archive className="h-6 w-6" aria-hidden="true" />}
          title="还没有 RunSnapshot"
          description="通过 TraceContract 向导验证映射后即可提交第一次构建。"
          action={
            <Link to="/trace-contracts/new" className={buttonVariants({ variant: "outline" })}>
              前往 Contract 向导
            </Link>
          }
        />
      ) : (
        <div className="space-y-3">
          {items.map((snapshot) => (
            <article key={snapshot.id} className="rounded-lg border bg-background p-4">
              <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
                <div className="min-w-0 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-semibold">{snapshot.name}</h2>
                    <SnapshotStatusBadge status={snapshot.status} />
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {snapshot.named_query_name ?? `Query #${snapshot.named_query_id}`} · Contract v
                    {snapshot.trace_contract_version}
                  </div>
                  <div className="flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-muted-foreground">
                    <span>source rows {snapshot.progress_source_rows}</span>
                    <span>runs {snapshot.progress_runs}</span>
                    <span>
                      content {snapshot.content_sha256?.slice(0, 12) ?? "pending"}
                    </span>
                    <span>{new Date(snapshot.created_at).toLocaleString()}</span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(snapshot.status === "failed" || snapshot.status === "corrupted") ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void retry(snapshot)}
                      disabled={createSnapshot.isPending}
                    >
                      <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />重试构建
                    </Button>
                  ) : null}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setExpandedId((current) => current === snapshot.id ? null : snapshot.id)}
                  >
                    {expandedId === snapshot.id ? "收起详情" : "查看详情"}
                  </Button>
                </div>
              </div>
              {snapshot.status === "building" ? (
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-label="Snapshot 构建中">
                  <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
                </div>
              ) : null}
              <SnapshotFailureState snapshot={snapshot} />
              {expandedId === snapshot.id ? <SnapshotDetail snapshotId={snapshot.id} /> : null}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

export function SnapshotFailureState({ snapshot }: { snapshot: RunSnapshotRead }) {
  if (snapshot.status !== "failed" && snapshot.status !== "corrupted") return null;
  return (
    <Alert variant="destructive" className="mt-4">
      <ShieldAlert className="h-4 w-4" aria-hidden="true" />
      <AlertTitle>
        {snapshot.status === "corrupted" ? "Artifact 已损坏" : "Snapshot 构建失败"}
      </AlertTitle>
      <AlertDescription>
        {snapshot.error?.code ?? "SNAPSHOT_ERROR"}: {snapshot.error?.message ?? "未知错误"}
      </AlertDescription>
    </Alert>
  );
}

function SnapshotDetail({ snapshotId }: { snapshotId: string }) {
  const snapshot = useRunSnapshot(snapshotId);
  if (snapshot.isLoading) return <LoadingState label="正在校验并加载 manifest…" rows={2} className="mt-4" />;
  if (snapshot.isError || snapshot.data === undefined) {
    return <ErrorState error={snapshot.error} title="Snapshot 详情不可用" className="mt-4" />;
  }
  return (
    <div className="mt-4 grid gap-4 border-t pt-4 lg:grid-cols-2">
      <div>
        <h3 className="mb-2 text-sm font-semibold">Integrity</h3>
        <dl className="space-y-2 break-all font-mono text-xs text-muted-foreground">
          <div><dt className="font-semibold text-foreground">artifact_sha256</dt><dd>{snapshot.data.artifact_sha256 ?? "N/A"}</dd></div>
          <div><dt className="font-semibold text-foreground">content_sha256</dt><dd>{snapshot.data.content_sha256 ?? "N/A"}</dd></div>
          <div><dt className="font-semibold text-foreground">size</dt><dd>{snapshot.data.artifact_size_bytes} bytes</dd></div>
        </dl>
      </div>
      <div>
        <h3 className="mb-2 text-sm font-semibold">Manifest</h3>
        <pre className="max-h-72 overflow-auto rounded-md bg-muted/40 p-3 text-xs">
          {JSON.stringify(snapshot.data.manifest, null, 2)}
        </pre>
      </div>
    </div>
  );
}

function SnapshotStatusBadge({ status }: { status: RunSnapshotRead["status"] }) {
  const label: Record<RunSnapshotRead["status"], string> = {
    building: "BUILDING",
    ready: "READY",
    failed: "FAILED",
    corrupted: "CORRUPTED",
    deleted: "DELETED",
  };
  return (
    <Badge
      variant={status === "ready" ? "default" : status === "building" ? "secondary" : "outline"}
      className={cn(
        (status === "failed" || status === "corrupted") &&
          "border-destructive/40 text-destructive",
      )}
    >
      {label[status]}
    </Badge>
  );
}
