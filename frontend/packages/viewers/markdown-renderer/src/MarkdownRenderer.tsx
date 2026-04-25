import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

import type { MarkdownRendererProps } from "./types";

import "./styles.css";

export function MarkdownRenderer({
  content,
  className,
  maxHeight,
}: MarkdownRendererProps) {
  return (
    <div
      className={["agentlens-markdown-renderer", className].filter(Boolean).join(" ")}
      style={maxHeight === undefined ? undefined : { maxHeight, overflow: "auto" }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a target="_blank" rel="noopener" {...props} />
          ),
          img: ({ node: _node, style, ...props }) => (
            <img style={{ maxWidth: "100%", ...style }} {...props} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
