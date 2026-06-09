import { useMemo, useState } from "react";
import { Clipboard } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const CLI_INSTALL = `python -m build
pipx install dist/agentlens-0.1.0-py3-none-any.whl`;
const CLI_VERIFY = "agentlens schema info";
const CLI_EXAMPLES = `agentlens data rows --query 42 --limit 100
agentlens context export --query 42
agentlens annotate --query 42 --row <row_identity> --color yellow --text "Suspicious pattern"`;

const MCP_INSTALL = `python -m build --outdir dist mcp_server
pipx install dist/agentlens_mcp-0.1.0-py3-none-any.whl`;
const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

export function AgentIntegrationTab() {
  const [backendUrl, setBackendUrl] = useState(DEFAULT_BACKEND_URL);
  const normalizedBackendUrl = backendUrl.trim();
  const backendUrlError = validateBackendUrl(normalizedBackendUrl);
  const mcpConfig = useMemo(
    () => buildMcpConfig(normalizedBackendUrl),
    [normalizedBackendUrl],
  );

  return (
    <div className="space-y-4">
      <section className="rounded-lg border bg-background p-5">
        <h2 className="text-base font-semibold">CLI</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          AgentLens CLI supports two modes:
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          <li>Live access: read current data from the backend</li>
          <li>Context export: materialize query data into local files for CLI agents</li>
        </ul>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <CodeBlock title="Install" code={CLI_INSTALL} />
          <CodeBlock title="Verify" code={CLI_VERIFY} />
          <CodeBlock title="Examples" code={CLI_EXAMPLES} />
        </div>
      </section>

      <section className="rounded-lg border bg-background p-5">
        <h2 className="text-base font-semibold">MCP Server</h2>
        <div className="mt-3 max-w-xl space-y-1.5">
          <label className="text-sm font-medium" htmlFor="agentlens-backend-url">
            Backend URL
          </label>
          <Input
            id="agentlens-backend-url"
            value={backendUrl}
            placeholder={DEFAULT_BACKEND_URL}
            onChange={(event) => setBackendUrl(event.target.value)}
            aria-invalid={backendUrlError !== null}
          />
          {backendUrlError !== null ? (
            <div className="text-xs text-destructive">{backendUrlError}</div>
          ) : null}
        </div>
        <div className="mt-4">
          <CodeBlock title="Install" code={MCP_INSTALL} />
        </div>
        <Tabs defaultValue="claude-code" className="mt-4">
          <TabsList>
            <TabsTrigger value="claude-code">Claude Code</TabsTrigger>
            <TabsTrigger value="claude-desktop">Claude Desktop</TabsTrigger>
            <TabsTrigger value="cursor">Cursor</TabsTrigger>
            <TabsTrigger value="generic">Generic MCP</TabsTrigger>
          </TabsList>
          <TabsContent value="claude-code">
            <CodeBlock
              title="Claude Code .mcp.json"
              code={mcpConfig.claudeCode}
              disabled={backendUrlError !== null}
              disabledMessage={backendUrlError ?? undefined}
            />
          </TabsContent>
          <TabsContent value="claude-desktop">
            <CodeBlock
              title="Claude Desktop config"
              code={mcpConfig.claudeDesktop}
              disabled={backendUrlError !== null}
              disabledMessage={backendUrlError ?? undefined}
            />
          </TabsContent>
          <TabsContent value="cursor">
            <CodeBlock
              title="Cursor config"
              code={mcpConfig.cursor}
              disabled={backendUrlError !== null}
              disabledMessage={backendUrlError ?? undefined}
            />
          </TabsContent>
          <TabsContent value="generic">
            <CodeBlock
              title="Generic MCP command"
              code={mcpConfig.generic}
              disabled={backendUrlError !== null}
              disabledMessage={backendUrlError ?? undefined}
            />
          </TabsContent>
        </Tabs>
      </section>

      <section className="rounded-lg border bg-background p-5">
        <h2 className="text-base font-semibold">Recommended Workflow</h2>
        <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
          <li>Run a query in AgentLens.</li>
          <li>Optionally select rows.</li>
          <li>Click Copy Agent Prompt.</li>
          <li>Paste into Claude Code / Codex / aider.</li>
          <li>Watch annotations appear in AgentLens in real time.</li>
        </ol>
      </section>
    </div>
  );
}

function CodeBlock({
  title,
  code,
  disabled = false,
  disabledMessage = "Backend URL is invalid",
}: {
  title: string;
  code: string;
  disabled?: boolean;
  disabledMessage?: string;
}) {
  async function handleCopy() {
    if (disabled) {
      toast.error(disabledMessage);
      return;
    }

    try {
      await navigator.clipboard.writeText(code);
      toast.success("Copied");
    } catch {
      window.prompt("Copy manually", code);
      toast.error("Copy failed; manual copy is available");
    }
  }

  return (
    <div className="overflow-hidden rounded-md border bg-muted/20">
      <div className="flex items-center justify-between gap-2 border-b bg-muted/40 px-3 py-2">
        <div className="text-sm font-medium">{title}</div>
        <Button variant="outline" size="sm" className="h-7 gap-1.5" onClick={handleCopy}>
          <Clipboard className="h-3.5 w-3.5" aria-hidden="true" />
          Copy
        </Button>
      </div>
      <pre className="overflow-x-auto p-3 text-xs">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function validateBackendUrl(value: string): string | null {
  if (value.length === 0) {
    return "Backend URL is required.";
  }

  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return "Backend URL must start with http:// or https://.";
    }
  } catch {
    return "Backend URL is not a valid URL.";
  }
  return null;
}

function buildMcpConfig(backendUrl: string) {
  return {
    claudeCode: buildJsonMcpConfig(backendUrl, "agent:claude-code"),
    claudeDesktop: buildJsonMcpConfig(backendUrl, "agent:claude-desktop"),
    cursor: buildJsonMcpConfig(backendUrl, "agent:cursor"),
    generic: `agentlens-mcp --backend-url ${backendUrl} --author agent:<client-name>`,
  };
}

function buildJsonMcpConfig(backendUrl: string, author: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        agentlens: {
          command: "agentlens-mcp",
          args: ["--backend-url", backendUrl, "--author", author],
        },
      },
    },
    null,
    2,
  );
}
