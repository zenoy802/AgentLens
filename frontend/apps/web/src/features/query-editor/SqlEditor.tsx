import { useEffect, useRef, useState } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";

import { cn } from "@/lib/utils";

const MIN_EDITOR_HEIGHT = 200;

type SqlEditorProps = {
  value: string;
  onChange: (value: string) => void;
  onRun: () => void;
  height?: number;
  onHeightChange?: (height: number) => void;
};

export function SqlEditor({ value, onChange, onRun, height, onHeightChange }: SqlEditorProps) {
  const [autoHeight, setAutoHeight] = useState(MIN_EDITOR_HEIGHT);
  const onRunRef = useRef(onRun);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    onRunRef.current = onRun;
  }, [onRun]);

  useEffect(() => {
    return () => cleanupRef.current?.();
  }, []);

  const handleMount: OnMount = (editor, monaco) => {
    const updateHeight = () => {
      const nextHeight = clampEditorHeight(editor.getContentHeight());
      setAutoHeight(nextHeight);
      onHeightChange?.(nextHeight);
      editor.layout({ width: editor.getLayoutInfo().width, height: nextHeight });
    };

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      onRunRef.current();
    });

    const subscription = editor.onDidContentSizeChange(updateHeight);
    cleanupRef.current = () => subscription.dispose();
    updateHeight();
  };

  const editorHeight = clampEditorHeight(height ?? autoHeight);

  return (
    <div className="overflow-hidden rounded-lg border bg-card">
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
