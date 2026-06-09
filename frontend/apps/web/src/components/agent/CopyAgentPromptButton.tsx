import { useMemo, useState } from "react";
import { Clipboard, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { createSelectionSnapshot } from "@/api/selectionSnapshots";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatApiError, getApiError } from "@/lib/formatApiError";
import { markAgentPromptCopied } from "@/lib/onboarding";
import type { ProductLanguage } from "@/lib/productLanguage";
import { useProductLanguageStore } from "@/stores/productLanguageStore";
import { useQueryStore } from "@/stores/queryStore";

const COPY_LABELS: Record<
  ProductLanguage,
  {
    button: string;
    copied: string;
  }
> = {
  "zh-CN": {
    button: "复制 Agent Prompt",
    copied: "Agent Prompt 已复制",
  },
  "en-US": {
    button: "Copy Agent Prompt",
    copied: "Agent prompt copied",
  },
};
const LARGE_SELECTION_THRESHOLD = 500;
const SELECTION_SNAPSHOT_TIMEOUT_MS = 15_000;

interface CopyAgentPromptButtonProps {
  queryId: number | null;
  disabled?: boolean;
}

export function CopyAgentPromptButton({
  queryId,
  disabled = false,
}: CopyAgentPromptButtonProps) {
  const selectedRowIds = useQueryStore((state) => state.selectedRowIds);
  const language = useProductLanguageStore((state) => state.language);
  const [copying, setCopying] = useState(false);
  const [manualPrompt, setManualPrompt] = useState<string | null>(null);
  const selectedRowIdentities = useMemo(
    () => Array.from(selectedRowIds),
    [selectedRowIds],
  );

  async function handleCopy() {
    if (queryId === null || copying) {
      return;
    }

    setCopying(true);
    try {
      let selectionId: string | null = null;
      if (selectedRowIdentities.length > 0) {
        if (selectedRowIdentities.length >= LARGE_SELECTION_THRESHOLD) {
          toast.info(`正在为 ${selectedRowIdentities.length} 行创建 selection snapshot`);
        }
        const snapshot = await withTimeout(
          createSelectionSnapshot(queryId, {
            row_identities: selectedRowIdentities,
            source: "copy_agent_prompt",
          }),
          SELECTION_SNAPSHOT_TIMEOUT_MS,
        );
        selectionId = snapshot.id;
      }

      const prompt = buildAgentPrompt({
        queryId,
        selectionId,
        selectedCount: selectedRowIdentities.length,
        language,
      });

      await copyPromptToClipboard(prompt);
      markAgentPromptCopied();
      toast.success(COPY_LABELS[language].copied);
    } catch (error) {
      if (error instanceof ClipboardWriteError) {
        setManualPrompt(error.prompt);
        toast.error("剪贴板写入失败，请手动复制");
        return;
      }
      if (getApiError(error)?.error.code === "SELECTION_TOO_LARGE") {
        toast.error("选择行数过多，请减少选择或使用 rows live access");
        return;
      }
      toast.error(formatApiError(error));
    } finally {
      setCopying(false);
    }
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          className="gap-2"
          disabled={disabled || queryId === null || copying}
          onClick={() => void handleCopy()}
        >
          {copying ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Clipboard className="h-4 w-4" aria-hidden="true" />
          )}
          {COPY_LABELS[language].button}
        </Button>
      </div>
      <Dialog open={manualPrompt !== null} onOpenChange={(open) => !open && setManualPrompt(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>手动复制 Agent Prompt</DialogTitle>
            <DialogDescription>剪贴板不可用，请从下方文本框复制。</DialogDescription>
          </DialogHeader>
          <textarea
            readOnly
            className="min-h-80 w-full resize-y rounded-md border bg-muted/20 p-3 font-mono text-xs"
            value={manualPrompt ?? ""}
            onFocus={(event) => event.currentTarget.select()}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(
      () => reject(new Error("Selection snapshot timed out. Please retry with fewer rows.")),
      timeoutMs,
    );
    promise.then(
      (value) => {
        window.clearTimeout(timeoutId);
        resolve(value);
      },
      (error: unknown) => {
        window.clearTimeout(timeoutId);
        reject(error);
      },
    );
  });
}

class ClipboardWriteError extends Error {
  constructor(readonly prompt: string) {
    super("Clipboard write failed.");
  }
}

async function copyPromptToClipboard(prompt: string) {
  try {
    if (navigator.clipboard === undefined) {
      throw new Error("Clipboard API is not available");
    }
    await navigator.clipboard.writeText(prompt);
  } catch (error) {
    throw new ClipboardWriteError(prompt);
  }
}

export function buildAgentPrompt({
  queryId,
  selectionId,
  selectedCount,
  language,
}: {
  queryId: number;
  selectionId: string | null;
  selectedCount: number;
  language: ProductLanguage;
}): string {
  const exportMcp =
    selectionId === null
      ? `export_context(query_id=${queryId}, scope="all")`
      : `export_context(query_id=${queryId}, selection_id="${selectionId}", scope="selection")`;
  const exportCli =
    selectionId === null
      ? `agentlens context export --query ${queryId}`
      : `agentlens context export --query ${queryId} --selection ${selectionId}`;
  const selectionDataEn =
    selectionId === null
      ? ""
      : `- selection_id: ${selectionId}
- selected_rows: ${selectedCount}
`;
  const selectionAccessEn =
    selectionId === null
      ? ""
      : `- MCP selected rows: get_selection("${selectionId}")
- CLI selected rows: agentlens data selection --selection ${selectionId}
`;
  const selectionDataZh =
    selectionId === null
      ? ""
      : `- selection_id：${selectionId}
- 已选择行数：${selectedCount}
`;
  const selectionAccessZh =
    selectionId === null
      ? ""
      : `- MCP 选中行：get_selection("${selectionId}")
- CLI 选中行：agentlens data selection --selection ${selectionId}
`;

  if (language === "zh-CN") {
    return `AgentLens 数据上下文：
- query_id：${queryId}
${selectionDataZh}
请使用 AgentLens MCP 工具或 \`agentlens\` CLI 先自行查看这个查询的数据和字段。不要预设分析目标、分析模式或打标方式。
回答语言要求：请始终使用中文回复我，包括澄清问题、分析结论和标注说明。

建议的数据入口：
- MCP 查询信息：get_query(query_id=${queryId})
- MCP 样例行：get_rows(query_id=${queryId}, limit=100, offset=0)
- CLI 查询信息：agentlens query show ${queryId}
- CLI 字段信息：agentlens schema columns --query ${queryId}
- CLI 样例行：agentlens data rows --query ${queryId} --limit 100
${selectionAccessZh}
数据量较大时：
- MCP：${exportMcp}
- CLI：${exportCli}

查看数据结构和可用字段后，请先问我想分析、排查或标注什么问题，再继续。`;
  }

  return `AgentLens data context:
- query_id: ${queryId}
${selectionDataEn}
Use AgentLens MCP tools or the \`agentlens\` CLI to inspect this query's data and fields first. Do not assume an analysis goal, analysis mode, or annotation workflow.
Response language requirement: Always reply to me in English, including follow-up questions, findings, and annotation text.

Suggested data access:
- MCP query info: get_query(query_id=${queryId})
- MCP sample rows: get_rows(query_id=${queryId}, limit=100, offset=0)
- CLI query info: agentlens query show ${queryId}
- CLI columns: agentlens schema columns --query ${queryId}
- CLI sample rows: agentlens data rows --query ${queryId} --limit 100
${selectionAccessEn}
For larger data:
- MCP: ${exportMcp}
- CLI: ${exportCli}

After you understand the data shape and available fields, ask me what I want to analyze, debug, or annotate before continuing.`;
}
