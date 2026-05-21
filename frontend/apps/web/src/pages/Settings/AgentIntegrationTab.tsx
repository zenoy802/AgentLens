import { Clipboard } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const CLI_INSTALL = "pipx install agentlens-cli";
const CLI_VERIFY = "agentlens schema info";
const CLI_EXAMPLES = `agentlens data rows --query 42 --limit 100
agentlens context export --query 42
agentlens annotate --query 42 --row <row_identity> --color yellow --text "Suspicious pattern"`;

const MCP_INSTALL = "pipx install agentlens-mcp";
const CLAUDE_CODE_CONFIG = `{
  "mcpServers": {
    "agentlens": {
      "command": "agentlens-mcp",
      "args": [
        "--backend-url", "http://127.0.0.1:8765",
        "--author", "agent:claude-code"
      ]
    }
  }
}`;
const CLAUDE_DESKTOP_CONFIG = `{
  "mcpServers": {
    "agentlens": {
      "command": "agentlens-mcp",
      "args": ["--backend-url", "http://127.0.0.1:8765", "--author", "agent:claude-desktop"]
    }
  }
}`;
const CURSOR_CONFIG = `{
  "mcpServers": {
    "agentlens": {
      "command": "agentlens-mcp",
      "args": ["--backend-url", "http://127.0.0.1:8765", "--author", "agent:cursor"]
    }
  }
}`;
const GENERIC_MCP_CONFIG = `agentlens-mcp --backend-url http://127.0.0.1:8765 --author agent:<client-name>`;

export function AgentIntegrationTab() {
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
            <CodeBlock title="Claude Code .mcp.json" code={CLAUDE_CODE_CONFIG} />
          </TabsContent>
          <TabsContent value="claude-desktop">
            <CodeBlock title="Claude Desktop config" code={CLAUDE_DESKTOP_CONFIG} />
          </TabsContent>
          <TabsContent value="cursor">
            <CodeBlock title="Cursor config" code={CURSOR_CONFIG} />
          </TabsContent>
          <TabsContent value="generic">
            <CodeBlock title="Generic MCP command" code={GENERIC_MCP_CONFIG} />
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

function CodeBlock({ title, code }: { title: string; code: string }) {
  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code);
      toast.success("Copied");
    } catch {
      toast.error("Copy failed");
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
