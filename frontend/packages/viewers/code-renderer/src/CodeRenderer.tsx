import { useMemo } from "react";
import hljs from "highlight.js/lib/core";
import json from "highlight.js/lib/languages/json";
import javascript from "highlight.js/lib/languages/javascript";
import plaintext from "highlight.js/lib/languages/plaintext";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";

import type { CodeRendererProps } from "./types";

import "./styles.css";

const REGISTERED_LANGUAGES = new Set<string>();

registerLanguage("sql", sql);
registerLanguage("python", python);
registerLanguage("javascript", javascript);
registerLanguage("typescript", typescript);
registerLanguage("json", json);
registerLanguage("plain", plaintext);
registerLanguage("plaintext", plaintext);

export function CodeRenderer({
  code,
  language,
  maxHeight,
  showLineNumbers = false,
}: CodeRendererProps) {
  const normalizedLanguage = normalizeLanguage(language);
  const highlighted = useMemo(
    () => highlightCode(code, normalizedLanguage),
    [code, normalizedLanguage],
  );
  const lines = useMemo(() => splitLines(highlighted), [highlighted]);

  function handleCopy() {
    if (typeof navigator === "undefined" || navigator.clipboard === undefined) {
      return;
    }

    void navigator.clipboard.writeText(code).catch(() => undefined);
  }

  return (
    <div className="agentlens-code-renderer relative rounded-md border bg-white text-sm">
      <button
        type="button"
        className="absolute right-2 top-2 z-10 rounded border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 shadow-sm hover:bg-slate-50"
        onClick={handleCopy}
      >
        Copy
      </button>
      <pre
        className="m-0 overflow-auto p-3 pr-16"
        style={maxHeight === undefined ? undefined : { maxHeight }}
      >
        <code className={`hljs language-${normalizedLanguage}`}>
          {showLineNumbers ? (
            lines.map((line, index) => (
              <span className="agentlens-code-line" key={index}>
                <span className="agentlens-code-line-number">{index + 1}</span>
                <span dangerouslySetInnerHTML={{ __html: line || " " }} />
              </span>
            ))
          ) : (
            <span dangerouslySetInnerHTML={{ __html: highlighted }} />
          )}
        </code>
      </pre>
    </div>
  );
}

function registerLanguage(name: string, language: Parameters<typeof hljs.registerLanguage>[1]) {
  if (REGISTERED_LANGUAGES.has(name)) {
    return;
  }

  hljs.registerLanguage(name, language);
  REGISTERED_LANGUAGES.add(name);
}

function normalizeLanguage(language: string): string {
  const normalized = language.toLowerCase();
  if (normalized === "js") {
    return "javascript";
  }
  if (normalized === "ts") {
    return "typescript";
  }
  if (normalized === "text") {
    return "plain";
  }
  return normalized;
}

function highlightCode(code: string, language: string): string {
  if (language === "plain" || language === "plaintext") {
    return hljs.highlight(code, { language: "plaintext", ignoreIllegals: true }).value;
  }

  if (hljs.getLanguage(language) === undefined) {
    return escapeHtml(code);
  }

  try {
    return hljs.highlight(code, { language, ignoreIllegals: true }).value;
  } catch {
    return escapeHtml(code);
  }
}

function splitLines(highlighted: string): string[] {
  return highlighted.split(/\r?\n/);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
