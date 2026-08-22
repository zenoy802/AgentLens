import { useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, CheckCircle2, DatabaseZap, Save } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useExecuteQuery } from "@/api/hooks/useExecute";
import { useQueries } from "@/api/hooks/useQueries";
import type { ExecutionResult, TraceContractRead } from "@/api/types";
import { ErrorState } from "@/components/common/ErrorState";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useCreateRunSnapshot,
  useCreateTraceContract,
  useValidateTraceContract,
} from "@/features/snapshots/api";
import {
  buildContractDefinition,
  ContractDraftError,
  isSensitiveSampleColumn,
  redactSensitiveSampleValue,
} from "@/features/snapshots/contractDraft";
import {
  EMPTY_CONTRACT_DRAFT,
  type ContractDraft,
  type TraceContractDefinition,
} from "@/features/snapshots/types";
import { formatApiError } from "@/lib/formatApiError";
import { cn } from "@/lib/utils";

const SAMPLE_LIMIT = 100;
const SAMPLE_PREVIEW_ROWS = 5;

export function TraceContractWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [draft, setDraft] = useState<ContractDraft>(EMPTY_CONTRACT_DRAFT);
  const [sample, setSample] = useState<ExecutionResult | null>(null);
  const [definition, setDefinition] = useState<TraceContractDefinition | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [focusedRow, setFocusedRow] = useState<number | null>(null);
  const [focusedPath, setFocusedPath] = useState<string | null>(null);
  const [savedContract, setSavedContract] = useState<TraceContractRead | null>(null);
  const queries = useQueries({ is_named: true, page_size: 100 });
  const executeQuery = useExecuteQuery();
  const validate = useValidateTraceContract();
  const createContract = useCreateTraceContract();
  const createSnapshot = useCreateRunSnapshot();

  const selectedQuery = queries.data?.items.find((query) => query.id === draft.namedQueryId);
  const safeColumns = useMemo(
    () => sample?.columns.filter((column) => !isSensitiveSampleColumn(column.name)) ?? [],
    [sample],
  );
  const hiddenColumnCount = (sample?.columns.length ?? 0) - safeColumns.length;

  function updateDraft<Key extends keyof ContractDraft>(key: Key, value: ContractDraft[Key]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setSavedContract(null);
    validate.reset();
  }

  async function loadSample() {
    if (draft.namedQueryId === null) {
      setDraftError("请选择命名查询。");
      return;
    }
    setDraftError(null);
    try {
      const result = await executeQuery.mutateAsync({
        queryId: draft.namedQueryId,
        payload: { row_limit: SAMPLE_LIMIT },
      });
      setSample(result);
      setFocusedRow(null);
      setFocusedPath(null);
      setStep(2);
    } catch (error) {
      setDraftError(formatApiError(error));
    }
  }

  async function runValidation() {
    if (draft.namedQueryId === null) return;
    try {
      const nextDefinition = buildContractDefinition(draft);
      setDefinition(nextDefinition);
      setDraftError(null);
      await validate.mutateAsync({
        named_query_id: draft.namedQueryId,
        definition: nextDefinition,
        sample_limit: SAMPLE_LIMIT,
      });
      setStep(3);
    } catch (error) {
      setDraftError(
        error instanceof ContractDraftError ? error.message : formatApiError(error),
      );
    }
  }

  async function saveContract() {
    if (
      draft.namedQueryId === null ||
      definition === null ||
      validate.data?.valid !== true ||
      draft.name.trim().length === 0
    ) {
      setDraftError("验证成功后请输入 contract 名称再保存。");
      return;
    }
    try {
      const contract = await createContract.mutateAsync({
        name: draft.name.trim(),
        named_query_id: draft.namedQueryId,
        definition,
      });
      setSavedContract(contract);
      toast.success(`TraceContract v${contract.version} 已保存`);
    } catch (error) {
      setDraftError(formatApiError(error));
    }
  }

  async function createFirstSnapshot() {
    if (savedContract === null || selectedQuery === undefined) return;
    try {
      await createSnapshot.mutateAsync({
        name: `${savedContract.name}-snapshot`,
        connection_id: selectedQuery.connection_id,
        named_query_id: selectedQuery.id,
        trace_contract_id: savedContract.id,
      });
      toast.success("Snapshot 构建已提交");
      navigate("/snapshots");
    } catch (error) {
      setDraftError(formatApiError(error));
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">新建 TraceContract</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            将任意 SQL 结果映射为可复现的 canonical trajectory。
          </p>
        </div>
        <Link to="/trace-contracts" className="text-sm text-muted-foreground hover:text-foreground">
          返回列表
        </Link>
      </div>

      <ol className="grid gap-3 md:grid-cols-3" aria-label="TraceContract 创建步骤">
        {["Layout 与样本", "字段与 outcome", "验证与预览"].map((label, index) => {
          const number = (index + 1) as 1 | 2 | 3;
          return (
            <li
              key={label}
              className={cn(
                "rounded-lg border px-4 py-3 text-sm",
                step === number ? "border-primary bg-primary/5 font-medium" : "text-muted-foreground",
              )}
              aria-current={step === number ? "step" : undefined}
            >
              {number}. {label}
            </li>
          );
        })}
      </ol>

      {draftError !== null ? (
        <Alert variant="destructive">
          <AlertTitle>无法继续</AlertTitle>
          <AlertDescription>{draftError}</AlertDescription>
        </Alert>
      ) : null}

      {step === 1 ? (
        <Card>
          <CardHeader>
            <CardTitle>1. 选择数据布局并加载安全样本</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-5 md:grid-cols-2">
            <label className="space-y-2 text-sm font-medium">
              命名查询
              <Select
                value={draft.namedQueryId === null ? undefined : String(draft.namedQueryId)}
                onValueChange={(value) => updateDraft("namedQueryId", Number(value))}
              >
                <SelectTrigger aria-label="命名查询">
                  <SelectValue placeholder="选择 query" />
                </SelectTrigger>
                <SelectContent>
                  {(queries.data?.items ?? []).map((query) => (
                    <SelectItem key={query.id} value={String(query.id)}>
                      {query.name ?? `Query #${query.id}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <label className="space-y-2 text-sm font-medium">
              Source layout
              <Select
                value={draft.sourceLayout}
                onValueChange={(value) =>
                  updateDraft("sourceLayout", value === "event_rows" ? "event_rows" : "run_rows")
                }
              >
                <SelectTrigger aria-label="Source layout">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="run_rows">一行一个 run（messages array）</SelectItem>
                  <SelectItem value="event_rows">一行一个 event</SelectItem>
                </SelectContent>
              </Select>
            </label>
            <div className="md:col-span-2 flex justify-end">
              <Button onClick={() => void loadSample()} disabled={executeQuery.isPending}>
                <DatabaseZap className="mr-2 h-4 w-4" aria-hidden="true" />
                {executeQuery.isPending ? "加载中…" : "加载最多 100 行样本"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === 2 ? (
        <Card>
          <CardHeader>
            <CardTitle>2. 映射字段与 outcome</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <SampleTable
              sample={sample}
              columns={safeColumns.map((column) => column.name)}
              hiddenColumnCount={hiddenColumnCount}
              focusedRow={focusedRow}
              focusedPath={focusedPath}
            />
            <div className="grid gap-4 md:grid-cols-3">
              <PathInput label="Contract name" value={draft.name} onChange={(value) => updateDraft("name", value)} />
              <PathInput label="Task ID *" value={draft.taskId} onChange={(value) => updateDraft("taskId", value)} />
              <PathInput label="Trace ID *" value={draft.traceId} onChange={(value) => updateDraft("traceId", value)} />
              <PathInput label="Trial ID" value={draft.trialId} onChange={(value) => updateDraft("trialId", value)} />
              <PathInput label="Pairing key" value={draft.pairingKey} onChange={(value) => updateDraft("pairingKey", value)} />
              <PathInput label="Outcome *" value={draft.outcome} onChange={(value) => updateDraft("outcome", value)} />
              <PathInput label="Score" value={draft.score} onChange={(value) => updateDraft("score", value)} />
              <PathInput label="Latency ms" value={draft.latencyMs} onChange={(value) => updateDraft("latencyMs", value)} />
              <PathInput label="Token usage" value={draft.tokenUsage} onChange={(value) => updateDraft("tokenUsage", value)} />
              <PathInput label="Cost USD" value={draft.costUsd} onChange={(value) => updateDraft("costUsd", value)} />
              <PathInput label="Run error" value={draft.error} onChange={(value) => updateDraft("error", value)} />
              <PathInput
                label={draft.sourceLayout === "run_rows" ? "Messages array *" : "Event index *"}
                value={draft.sourceLayout === "run_rows" ? draft.messages : draft.eventIndex}
                onChange={(value) =>
                  updateDraft(draft.sourceLayout === "run_rows" ? "messages" : "eventIndex", value)
                }
              />
              <PathInput label="Role" value={draft.role} onChange={(value) => updateDraft("role", value)} />
              <PathInput label="Content *" value={draft.content} onChange={(value) => updateDraft("content", value)} />
              <PathInput label="Kind" value={draft.kind} onChange={(value) => updateDraft("kind", value)} />
              <PathInput label="Status" value={draft.status} onChange={(value) => updateDraft("status", value)} />
              <PathInput label="Tool calls" value={draft.toolCalls} onChange={(value) => updateDraft("toolCalls", value)} />
              <PathInput label="Tool call ID" value={draft.toolCallId} onChange={(value) => updateDraft("toolCallId", value)} />
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <PathInput label="Success values (JSON array)" value={draft.successValues} onChange={(value) => updateDraft("successValues", value)} />
              <PathInput label="Failure values (JSON array)" value={draft.failureValues} onChange={(value) => updateDraft("failureValues", value)} />
              <PathInput label="Abstain values (JSON array)" value={draft.abstainValues} onChange={(value) => updateDraft("abstainValues", value)} />
            </div>
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep(1)}>
                <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />返回
              </Button>
              <Button onClick={() => void runValidation()} disabled={validate.isPending}>
                {validate.isPending ? "验证中…" : "验证并预览"}
                <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {step === 3 ? (
        <Card>
          <CardHeader>
            <CardTitle>3. 验证结果与 canonical preview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {validate.isError ? <ErrorState error={validate.error} /> : null}
            {validate.data !== undefined ? (
              <>
                <Alert variant={validate.data.valid ? "default" : "destructive"}>
                  <AlertTitle>
                    {validate.data.valid ? "Contract 验证通过" : "Contract 验证失败"}
                  </AlertTitle>
                  <AlertDescription>
                    {validate.data.valid_run_count} 个有效 run；pairing-key field coverage {" "}
                    {(validate.data.pairing_key_field_coverage * 100).toFixed(1)}%。
                  </AlertDescription>
                </Alert>
                {validate.data.errors.length > 0 ? (
                  <div className="space-y-2" aria-label="验证错误列表">
                    {validate.data.errors.map((issue, index) => (
                      <button
                        key={`${issue.code}-${index}`}
                        type="button"
                        className="block w-full rounded-md border border-destructive/30 p-3 text-left text-sm hover:bg-destructive/5"
                        onClick={() => {
                          setFocusedRow(issue.source_row_index ?? null);
                          setFocusedPath(issue.path ?? null);
                          setStep(2);
                        }}
                      >
                        <span className="font-medium">{issue.code}</span>: {issue.reason}
                        {issue.path !== null && issue.path !== undefined ? ` · ${issue.path}` : ""}
                        {issue.source_row_index !== null && issue.source_row_index !== undefined
                          ? ` · row ${issue.source_row_index}`
                          : ""}
                      </button>
                    ))}
                  </div>
                ) : null}
                {validate.data.diagnostics.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {validate.data.diagnostics.map((diagnostic, index) => (
                      <Badge key={`${diagnostic.code}-${index}`} variant="secondary">
                        {diagnostic.code} · row {diagnostic.source_row_index}
                      </Badge>
                    ))}
                  </div>
                ) : null}
                <div>
                  <h2 className="mb-2 text-sm font-semibold">Canonical preview</h2>
                  <pre className="max-h-[420px] overflow-auto rounded-lg border bg-muted/30 p-4 text-xs">
                    {JSON.stringify(validate.data.canonical_preview, null, 2)}
                  </pre>
                </div>
              </>
            ) : null}
            {savedContract !== null ? (
              <Alert>
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                <AlertTitle>TraceContract v{savedContract.version} 已保存</AlertTitle>
                <AlertDescription>
                  现在可用已保存的 query 与 contract 构建 immutable snapshot。
                </AlertDescription>
              </Alert>
            ) : null}
            <div className="flex flex-wrap justify-between gap-3">
              <Button variant="outline" onClick={() => setStep(2)}>
                <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />修改映射
              </Button>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => void saveContract()}
                  disabled={createContract.isPending || validate.data?.valid !== true}
                >
                  <Save className="mr-2 h-4 w-4" aria-hidden="true" />
                  {createContract.isPending ? "保存中…" : "保存 Contract"}
                </Button>
                <Button
                  onClick={() => void createFirstSnapshot()}
                  disabled={savedContract === null || createSnapshot.isPending}
                >
                  {createSnapshot.isPending ? "提交中…" : "创建 Snapshot"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

type PathInputProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
};

function PathInput({ label, value, onChange }: PathInputProps) {
  return (
    <label className="space-y-2 text-sm font-medium">
      {label}
      <Input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

type SampleTableProps = {
  sample: ExecutionResult | null;
  columns: string[];
  hiddenColumnCount: number;
  focusedRow: number | null;
  focusedPath: string | null;
};

function SampleTable({
  sample,
  columns,
  hiddenColumnCount,
  focusedRow,
  focusedPath,
}: SampleTableProps) {
  if (sample === null) return null;
  const visibleRowIndexes = Array.from(
    { length: Math.min(sample.rows.length, SAMPLE_PREVIEW_ROWS) },
    (_, index) => index,
  );
  if (
    focusedRow !== null &&
    focusedRow >= SAMPLE_PREVIEW_ROWS &&
    focusedRow < sample.rows.length
  ) {
    visibleRowIndexes.push(focusedRow);
  }
  return (
    <section aria-labelledby="sample-title" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="sample-title" className="text-sm font-semibold">
          Source sample（前 {Math.min(sample.rows.length, SAMPLE_PREVIEW_ROWS)} 行）
        </h2>
        {hiddenColumnCount > 0 ? (
          <Badge variant="secondary">已隐藏 {hiddenColumnCount} 个敏感列</Badge>
        ) : null}
      </div>
      {focusedRow !== null || focusedPath !== null ? (
        <div className="text-xs font-medium text-amber-700" role="status">
          验证错误定位：{focusedRow === null ? "row 未知" : `row ${focusedRow}`}
          {focusedPath === null ? "" : ` · path ${focusedPath}`}
        </div>
      ) : null}
      <div className="overflow-x-auto rounded-lg border">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-3 py-2">row</th>
              {columns.map((column) => (
                <th key={column} className="px-3 py-2 font-medium">{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRowIndexes.map((index) => {
              const row = sample.rows[index];
              return (
                <tr
                  key={index}
                  className={cn("border-t", focusedRow === index && "bg-amber-50")}
                >
                  <td className="px-3 py-2 font-mono">{index}</td>
                  {columns.map((column) => (
                    <td key={column} className="max-w-64 truncate px-3 py-2 font-mono">
                      {formatCell(row[column])}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function formatCell(value: unknown): string {
  const safeValue = redactSensitiveSampleValue(value);
  if (typeof safeValue === "string") return safeValue;
  try {
    return JSON.stringify(safeValue);
  } catch {
    return String(safeValue);
  }
}
