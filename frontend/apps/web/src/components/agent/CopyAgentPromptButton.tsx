import { useMemo, useState } from "react";
import { Clipboard, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { createSelectionSnapshot } from "@/api/selectionSnapshots";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatApiError } from "@/lib/formatApiError";
import { useQueryStore } from "@/stores/queryStore";

type AnalysisHint =
  | "failure modes"
  | "consistency issues"
  | "performance outliers"
  | "labeling suggestions"
  | "custom";

const ANALYSIS_HINTS: AnalysisHint[] = [
  "failure modes",
  "consistency issues",
  "performance outliers",
  "labeling suggestions",
  "custom",
];

interface CopyAgentPromptButtonProps {
  queryId: number | null;
  disabled?: boolean;
}

export function CopyAgentPromptButton({
  queryId,
  disabled = false,
}: CopyAgentPromptButtonProps) {
  const selectedRowIds = useQueryStore((state) => state.selectedRowIds);
  const [analysisHint, setAnalysisHint] = useState<AnalysisHint>("failure modes");
  const [customHint, setCustomHint] = useState("");
  const [copying, setCopying] = useState(false);
  const selectedRowIdentities = useMemo(
    () => Array.from(selectedRowIds),
    [selectedRowIds],
  );
  const resolvedHint =
    analysisHint === "custom"
      ? customHint.trim() || "custom analysis"
      : analysisHint;

  async function handleCopy() {
    if (queryId === null || copying) {
      return;
    }

    setCopying(true);
    try {
      let selectionId: string | null = null;
      if (selectedRowIdentities.length > 0) {
        const snapshot = await createSelectionSnapshot(queryId, {
          row_identities: selectedRowIdentities,
          source: "copy_agent_prompt",
        });
        selectionId = snapshot.id;
      }

      const prompt = buildAgentPrompt({
        queryId,
        selectionId,
        selectedCount: selectedRowIdentities.length,
        analysisHint: resolvedHint,
      });

      if (navigator.clipboard === undefined) {
        throw new Error("Clipboard API is not available");
      }
      await navigator.clipboard.writeText(prompt);
      toast.success("Agent prompt copied");
    } catch (error) {
      toast.error(formatApiError(error));
    } finally {
      setCopying(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        value={analysisHint}
        onValueChange={(value) => setAnalysisHint(value as AnalysisHint)}
      >
        <SelectTrigger className="h-9 w-48">
          <SelectValue placeholder="Analysis hint" />
        </SelectTrigger>
        <SelectContent>
          {ANALYSIS_HINTS.map((hint) => (
            <SelectItem key={hint} value={hint}>
              {hint === "custom" ? "custom..." : hint}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {analysisHint === "custom" ? (
        <Input
          value={customHint}
          maxLength={120}
          className="h-9 w-56"
          placeholder="Short analysis focus"
          onChange={(event) => setCustomHint(event.target.value)}
        />
      ) : null}
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
        Copy Agent Prompt
      </Button>
    </div>
  );
}

export function buildAgentPrompt({
  queryId,
  selectionId,
  selectedCount,
  analysisHint,
}: {
  queryId: number;
  selectionId: string | null;
  selectedCount: number;
  analysisHint: string;
}): string {
  const selectionPart =
    selectionId === null
      ? ""
      : `I selected ${selectedCount} rows in the UI. selection_id="${selectionId}".\n`;
  const exportMcp =
    selectionId === null
      ? `export_context(query_id=${queryId}, scope="all")`
      : `export_context(query_id=${queryId}, selection_id="${selectionId}", scope="selection")`;
  const exportCli =
    selectionId === null
      ? `agentlens context export --query ${queryId}`
      : `agentlens context export --query ${queryId} --selection ${selectionId}`;
  const selectionWorkflow =
    selectionId === null
      ? ""
      : `1. If a selection_id is provided, start with:
   - MCP: get_selection("${selectionId}")
   - CLI: agentlens data selection --selection ${selectionId}

`;
  const firstNumber = selectionId === null ? 1 : 2;

  return `I'm analyzing AgentLens query_id=${queryId}.
${selectionPart}
Please use AgentLens MCP tools or the \`agentlens\` CLI to inspect the data.

Recommended workflow:
${selectionWorkflow}${firstNumber}. For small or interactive analysis, use live access:
   - MCP: get_rows(query_id=${queryId}, limit=100, offset=0)
   - CLI: agentlens data rows --query ${queryId} --limit 100

${firstNumber + 1}. For larger analysis, export a local context:
   - MCP: ${exportMcp}
   - CLI: ${exportCli}

${firstNumber + 2}. Analyze for: ${analysisHint}

${firstNumber + 3}. Write findings back to AgentLens:
   - Use highlight_rows() for row-level findings.
   - Use add_annotation() for cell-level pinpointing.

Color conventions:
- red: hard failures / errors
- yellow: suspicious / warnings
- green: verified-correct / success cases
- blue: informational notes
- gray: neutral notes

Please include concise explanations in annotation text so they are useful in the AgentLens UI.`;
}
