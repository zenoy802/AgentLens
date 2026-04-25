export type CodeLanguage = "sql" | "python" | "javascript" | "typescript" | "json" | "plain" | string;

export interface CodeRendererProps {
  code: string;
  language: CodeLanguage;
  maxHeight?: number;
  showLineNumbers?: boolean;
}
