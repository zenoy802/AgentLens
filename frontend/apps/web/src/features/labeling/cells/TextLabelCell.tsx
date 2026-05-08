import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";

import { useQueuedUpsertLabel } from "@/api/hooks/useLabels";
import { cn } from "@/lib/utils";
import {
  coerceStringValue,
  type TextLabelField,
} from "@/features/labeling/cells/utils";

type TextLabelCellProps = {
  queryId: number;
  resultKey: string | null;
  field: TextLabelField;
  rowId: string;
  value: unknown;
};

const SAVE_DEBOUNCE_MS = 500;

export function TextLabelCell({
  queryId,
  resultKey,
  field,
  rowId,
  value,
}: TextLabelCellProps) {
  const { commitLabel } = useQueuedUpsertLabel(queryId, resultKey);
  const textValue = coerceStringValue(value);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(textValue ?? "");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const saveTimeoutRef = useRef<number | null>(null);
  const pendingSaveRef = useRef<string | null>(null);
  const draftRef = useRef(draft);
  const dirtyRef = useRef(false);
  const editingRef = useRef(editing);
  const latestSaveContextRef = useRef({
    commitLabel,
    fieldKey: field.key,
    rowId,
    textValue: textValue ?? "",
  });

  useEffect(() => {
    latestSaveContextRef.current = {
      commitLabel,
      fieldKey: field.key,
      rowId,
      textValue: textValue ?? "",
    };
    dirtyRef.current = draftRef.current !== (textValue ?? "");
  }, [commitLabel, field.key, rowId, textValue]);

  useEffect(() => {
    editingRef.current = editing;
  }, [editing]);

  useEffect(() => {
    if (!editing) {
      const nextValue = textValue ?? "";
      draftRef.current = nextValue;
      dirtyRef.current = false;
      setDraft(nextValue);
    }
  }, [editing, textValue]);

  useEffect(() => {
    if (editing) {
      textareaRef.current?.focus();
      textareaRef.current?.select();
    }
  }, [editing]);

  const saveValue = useCallback((nextValue: string, updateEditing: boolean) => {
    clearSaveTimeout(saveTimeoutRef);
    pendingSaveRef.current = null;
    dirtyRef.current = false;
    if (updateEditing) {
      setEditing(false);
    }

    const context = latestSaveContextRef.current;
    if (nextValue === context.textValue) {
      return;
    }
    void context.commitLabel({
      rowIdentity: context.rowId,
      fieldKey: context.fieldKey,
      value: nextValue,
    });
  }, []);

  const flushPendingSave = useCallback(
    (updateEditing: boolean) => {
      const pendingValue = pendingSaveRef.current;
      if (pendingValue !== null) {
        saveValue(pendingValue, updateEditing);
        return;
      }
      if (editingRef.current && dirtyRef.current) {
        saveValue(draftRef.current, updateEditing);
        return;
      }
      clearSaveTimeout(saveTimeoutRef);
    },
    [saveValue],
  );

  useEffect(
    () => () => {
      flushPendingSave(false);
    },
    [flushPendingSave],
  );

  function commit(nextValue: string) {
    saveValue(nextValue, true);
  }

  function scheduleCommit() {
    clearSaveTimeout(saveTimeoutRef);
    pendingSaveRef.current = draftRef.current;
    saveTimeoutRef.current = window.setTimeout(
      () => flushPendingSave(true),
      SAVE_DEBOUNCE_MS,
    );
  }

  function cancel() {
    clearSaveTimeout(saveTimeoutRef);
    pendingSaveRef.current = null;
    dirtyRef.current = false;
    draftRef.current = textValue ?? "";
    setDraft(textValue ?? "");
    setEditing(false);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      cancel();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      commit(draftRef.current);
    }
  }

  if (editing) {
    return (
      <textarea
        ref={textareaRef}
        data-row-click-stop
        className={cn(
          "h-full min-h-8 w-full resize-none rounded-md border bg-background px-2 py-1 text-xs shadow-sm",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        )}
        value={draft}
        onChange={(event) => {
          const nextValue = event.target.value;
          draftRef.current = nextValue;
          dirtyRef.current = nextValue !== latestSaveContextRef.current.textValue;
          setDraft(nextValue);
        }}
        onBlur={scheduleCommit}
        onKeyDown={handleKeyDown}
      />
    );
  }

  return (
    <button
      type="button"
      data-row-click-stop
      className={cn(
        "flex h-full min-w-0 flex-1 items-center rounded px-1 text-left",
        "hover:bg-accent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
      )}
      title={textValue ?? undefined}
      onClick={() => setEditing(true)}
    >
      {textValue === null ? (
        <span className="text-xs text-muted-foreground">未标</span>
      ) : textValue.length === 0 ? (
        <span className="text-xs text-muted-foreground">空白</span>
      ) : (
        <span className="min-w-0 truncate text-xs text-foreground">{textValue}</span>
      )}
    </button>
  );
}

function clearSaveTimeout(timeoutRef: { current: number | null }) {
  if (timeoutRef.current !== null) {
    window.clearTimeout(timeoutRef.current);
    timeoutRef.current = null;
  }
}
