import { isValid, parseISO } from "date-fns";

import { TextCell } from "@/features/row-view/cells/TextCell";

interface TimestampCellProps {
  value: unknown;
  format: string;
}

export function TimestampCell({ value, format }: TimestampCellProps) {
  if (value == null) {
    return <span className="text-muted-foreground">NULL</span>;
  }

  const date = parseDate(value);
  if (date === null || !isValid(date)) {
    return <TextCell value={value} />;
  }

  try {
    const formatted = formatUtcDate(date, format);
    return (
      <div className="truncate" title={formatted}>
        {formatted}
      </div>
    );
  } catch {
    return <TextCell value={value} />;
  }
}

function parseDate(value: unknown): Date | null {
  if (value instanceof Date) {
    return value;
  }

  if (typeof value === "string") {
    return parseISO(normalizeIsoTimestamp(value));
  }

  if (typeof value === "number") {
    return new Date(value);
  }

  return null;
}

function normalizeIsoTimestamp(value: string): string {
  const normalized = value.trim().replace(/\s+/, "T");
  if (hasExplicitTimeZone(normalized)) {
    return normalized;
  }

  if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    return `${normalized}T00:00:00Z`;
  }

  return `${normalized}Z`;
}

function hasExplicitTimeZone(value: string): boolean {
  return /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
}

function formatUtcDate(date: Date, format: string): string {
  const replacements: Record<string, string> = {
    YYYY: pad(date.getUTCFullYear(), 4),
    yyyy: pad(date.getUTCFullYear(), 4),
    YY: pad(date.getUTCFullYear() % 100, 2),
    yy: pad(date.getUTCFullYear() % 100, 2),
    MM: pad(date.getUTCMonth() + 1, 2),
    DD: pad(date.getUTCDate(), 2),
    dd: pad(date.getUTCDate(), 2),
    HH: pad(date.getUTCHours(), 2),
    mm: pad(date.getUTCMinutes(), 2),
    ss: pad(date.getUTCSeconds(), 2),
    SSS: pad(date.getUTCMilliseconds(), 3),
  };

  return format.replace(/YYYY|yyyy|YY|yy|MM|DD|dd|HH|mm|ss|SSS/g, (token) => replacements[token]);
}

function pad(value: number, length: number): string {
  return String(value).padStart(length, "0");
}
