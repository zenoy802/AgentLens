import { useEffect, useRef, useState } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";

import { cn } from "@/lib/utils";

export const MIN_EDITOR_HEIGHT = 120;

type MonacoEditor = Parameters<OnMount>[0];

type SqlEditorProps = {
  value: string;
  onChange: (value: string) => void;
  onRun: () => void;
  height?: number;
  onHeightChange?: (height: number) => void;
  framed?: boolean;
};

export function SqlEditor({
  value,
  onChange,
  onRun,
  height,
  onHeightChange,
  framed = true,
}: SqlEditorProps) {
  const [autoHeight, setAutoHeight] = useState(MIN_EDITOR_HEIGHT);
  const onRunRef = useRef(onRun);
  const editorRef = useRef<MonacoEditor | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    onRunRef.current = onRun;
  }, [onRun]);

  useEffect(() => {
    return () => cleanupRef.current?.();
  }, []);

  const editorHeight = clampEditorHeight(height ?? autoHeight);

  useEffect(() => {
    const editor = editorRef.current;
    if (editor === null) {
      return;
    }

    editor.layout({
      width: editor.getLayoutInfo().width,
      height: editorHeight,
    });
  }, [editorHeight]);

  const handleMount: OnMount = (editor, monaco) => {
    cleanupRef.current?.();
    editorRef.current = editor;

    const updateAutoHeight = () => {
      const nextHeight = clampEditorHeight(editor.getContentHeight());
      setAutoHeight(nextHeight);
      onHeightChange?.(nextHeight);
    };

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      onRunRef.current();
    });

    const subscription = editor.onDidContentSizeChange(updateAutoHeight);
    cleanupRef.current = () => {
      subscription.dispose();
      editorRef.current = null;
    };
    updateAutoHeight();
  };

  return (
    <div className={cn(framed && "overflow-hidden rounded-lg border bg-card")}>
      <Editor
        className={cn("font-mono")}
        height={editorHeight}
        language="sql"
        theme="light"
        value={value}
        loading={<div className="p-4 text-sm text-muted-foreground">加载 SQL 编辑器...</div>}
        onChange={(nextValue) => onChange(nextValue ?? "")}
        onMount={handleMount}
        options={{
          automaticLayout: true,
          fontSize: 13,
          lineNumbers: "on",
          minimap: { enabled: false },
          padding: { top: 12, bottom: 12 },
          scrollbar: { alwaysConsumeMouseWheel: false },
          scrollBeyondLastLine: false,
          wordWrap: "on",
        }}
      />
    </div>
  );
}

export function clampEditorHeight(height: number): number {
  const maxHeight = Math.max(MIN_EDITOR_HEIGHT, Math.floor(window.innerHeight * 0.5));
  return Math.min(Math.max(height, MIN_EDITOR_HEIGHT), maxHeight);
}
