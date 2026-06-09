import { useEffect, type RefObject } from "react";

import type { LabelField, LabelOption } from "@/api/types";

export type SingleSelectLabelField = Extract<LabelField, { type: "single_select" }>;
export type MultiSelectLabelField = Extract<LabelField, { type: "multi_select" }>;
export type TextLabelField = Extract<LabelField, { type: "text" }>;

export function getLabelOptions(
  field: SingleSelectLabelField | MultiSelectLabelField,
): LabelOption[] {
  return field.options ?? [];
}

export function getOptionByValue(
  options: LabelOption[],
  value: string,
): LabelOption | undefined {
  return options.find((option) => option.value === value);
}

export function coerceStringValue(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export function coerceStringArrayValue(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

export function labelValuesEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) {
    return true;
  }
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
    return false;
  }
  const leftValues = [...left].sort();
  const rightValues = [...right].sort();
  return leftValues.every((item, index) => item === rightValues[index]);
}

export function labelFieldsEqual(left: LabelField, right: LabelField): boolean {
  if (left.key !== right.key || left.label !== right.label || left.type !== right.type) {
    return false;
  }

  if (left.type === "text" && right.type === "text") {
    return true;
  }
  if (left.type === "text" || right.type === "text") {
    return false;
  }

  const leftOptions = getLabelOptions(left);
  const rightOptions = getLabelOptions(right);
  if (leftOptions.length !== rightOptions.length) {
    return false;
  }

  return leftOptions.every((option, index) => {
    const other = rightOptions[index];
    return (
      option.value === other.value &&
      option.label === other.label &&
      (option.color ?? null) === (other.color ?? null)
    );
  });
}

export function useCloseOnRowTableScroll(
  open: boolean,
  setOpen: (open: boolean) => void,
  triggerRef: RefObject<HTMLElement>,
) {
  useEffect(() => {
    if (!open) {
      return;
    }

    const container = triggerRef.current?.closest("[data-row-table-container]");
    if (container === null || container === undefined) {
      return;
    }

    function close() {
      setOpen(false);
    }

    container.addEventListener("scroll", close, { passive: true });
    return () => container.removeEventListener("scroll", close);
  }, [open, setOpen, triggerRef]);
}
