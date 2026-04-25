import { useMemo, useState } from "react";

import type { JsonRendererProps } from "./types";

type JsonNodeProps = {
  name?: string;
  value: unknown;
  depth: number;
  collapsed: boolean;
  maxDepth: number;
};

type ExpandableNodeProps = Omit<JsonNodeProps, "value"> & {
  value: Record<string, unknown> | unknown[];
};

const INDENT_PX = 16;

export function JsonRenderer({
  value,
  collapsed = true,
  maxDepth = 10,
  className,
}: JsonRendererProps) {
  const copyText = useMemo(() => stringifyJson(value, 2), [value]);

  function handleCopy() {
    if (typeof navigator === "undefined" || navigator.clipboard === undefined) {
      return;
    }

    void navigator.clipboard.writeText(copyText).catch(() => undefined);
  }

  return (
    <div
      className={[
        "agentlens-json-renderer relative rounded-md border bg-white p-3 font-mono text-xs leading-6 text-slate-900",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <button
        type="button"
        className="absolute right-2 top-2 rounded border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 shadow-sm hover:bg-slate-50"
        onClick={handleCopy}
      >
        Copy
      </button>
      <div className="overflow-auto pr-14">
        <JsonNode value={value} depth={0} collapsed={collapsed} maxDepth={maxDepth} />
      </div>
    </div>
  );
}

function JsonNode({ name, value, depth, collapsed, maxDepth }: JsonNodeProps) {
  if (isExpandable(value)) {
    return (
      <ExpandableNode
        name={name}
        value={value}
        depth={depth}
        collapsed={collapsed}
        maxDepth={maxDepth}
      />
    );
  }

  return (
    <div className="min-w-0 whitespace-pre-wrap break-words" style={nodeIndent(depth)}>
      {name !== undefined ? <PropertyName name={name} /> : null}
      <PrimitiveValue value={value} />
    </div>
  );
}

function ExpandableNode({ name, value, depth, collapsed, maxDepth }: ExpandableNodeProps) {
  const forcedByDepth = depth >= maxDepth;
  const [isCollapsed, setIsCollapsed] = useState(collapsed || forcedByDepth);
  const entries = getEntries(value);
  const isArray = Array.isArray(value);
  const openToken = isArray ? "[" : "{";
  const closeToken = isArray ? "]" : "}";
  const summary = getSummary(value);

  if (isCollapsed) {
    return (
      <div className="min-w-0 whitespace-pre-wrap break-words" style={nodeIndent(depth)}>
        <ToggleButton
          expanded={false}
          onClick={() => setIsCollapsed(false)}
          label={forcedByDepth ? "展开超过最大深度的 JSON 节点" : "展开 JSON 节点"}
        />
        {name !== undefined ? <PropertyName name={name} /> : null}
        <span className="text-slate-500">
          {openToken}
          {forcedByDepth ? "..." : summary}
          {closeToken}
        </span>
      </div>
    );
  }

  return (
    <div>
      <div className="min-w-0 whitespace-pre-wrap break-words" style={nodeIndent(depth)}>
        <ToggleButton expanded onClick={() => setIsCollapsed(true)} label="折叠 JSON 节点" />
        {name !== undefined ? <PropertyName name={name} /> : null}
        <span className="text-slate-500">{openToken}</span>
      </div>
      {entries.length > 0 ? (
        entries.map(([entryName, entryValue]) => (
          <JsonNode
            key={entryName}
            name={isArray ? undefined : entryName}
            value={entryValue}
            depth={depth + 1}
            collapsed={collapsed}
            maxDepth={maxDepth}
          />
        ))
      ) : (
        <div className="text-slate-400" style={nodeIndent(depth + 1)}>
          empty
        </div>
      )}
      <div className="text-slate-500" style={nodeIndent(depth)}>
        {closeToken}
      </div>
    </div>
  );
}

function ToggleButton({
  expanded,
  onClick,
  label,
}: {
  expanded: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      className="mr-1 inline-flex h-4 w-4 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-900"
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      {expanded ? "▾" : "▸"}
    </button>
  );
}

function PropertyName({ name }: { name: string }) {
  return <span className="text-slate-700">"{name}": </span>;
}

function PrimitiveValue({ value }: { value: unknown }) {
  if (typeof value === "string") {
    return <span className="text-emerald-700">"{value}"</span>;
  }

  if (typeof value === "number") {
    return <span className="text-blue-700">{String(value)}</span>;
  }

  if (typeof value === "boolean") {
    return <span className="text-purple-700">{String(value)}</span>;
  }

  if (value === null) {
    return <span className="text-slate-400">null</span>;
  }

  if (value === undefined) {
    return <span className="text-slate-400">undefined</span>;
  }

  return <span className="text-slate-700">{safeString(value)}</span>;
}

function isExpandable(value: unknown): value is Record<string, unknown> | unknown[] {
  return typeof value === "object" && value !== null;
}

function getEntries(value: Record<string, unknown> | unknown[]): Array<[string, unknown]> {
  if (Array.isArray(value)) {
    return value.map((item, index) => [String(index), item]);
  }

  return Object.entries(value);
}

function getSummary(value: Record<string, unknown> | unknown[]): string {
  if (Array.isArray(value)) {
    return value.length === 0 ? "" : `${value.length} items`;
  }

  const count = Object.keys(value).length;
  return count === 0 ? "" : `${count} keys`;
}

function nodeIndent(depth: number): { paddingLeft: number } {
  return { paddingLeft: depth * INDENT_PX };
}

function stringifyJson(value: unknown, spaces?: number): string {
  try {
    const json = JSON.stringify(value, stringifyReplacer(), spaces);
    return json ?? safeString(value);
  } catch {
    return safeString(value);
  }
}

function stringifyReplacer(): (key: string, value: unknown) => unknown {
  const seen = new WeakSet<object>();

  return (_key: string, value: unknown): unknown => {
    if (typeof value === "bigint") {
      return value.toString();
    }
    if (typeof value === "object" && value !== null) {
      if (seen.has(value)) {
        return "[Circular]";
      }
      seen.add(value);
    }
    return value;
  };
}

function safeString(value: unknown): string {
  try {
    return String(value);
  } catch {
    return "[unserializable value]";
  }
}
