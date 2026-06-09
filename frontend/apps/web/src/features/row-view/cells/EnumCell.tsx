import { Badge } from "@/components/ui/badge";

type EnumCellProps = {
  value: unknown;
  colors?: Record<string, string>;
};

const ENUM_COLOR_PALETTE = [
  "#10b981",
  "#f59e0b",
  "#f43f5e",
  "#6366f1",
  "#0ea5e9",
  "#8b5cf6",
  "#06b6d4",
  "#84cc16",
  "#64748b",
  "#ef4444",
] as const;

export function EnumCell({ value, colors = {} }: EnumCellProps) {
  const values = toEnumValues(value);
  if (values.length === 0) {
    return <span className="text-muted-foreground">-</span>;
  }

  const [firstValue] = values;
  const hiddenCount = values.length - 1;

  return (
    <div className="flex h-6 max-w-full items-center gap-1 overflow-hidden">
      <EnumBadge value={firstValue} color={colors[firstValue] ?? getEnumColor(firstValue)} />
      {hiddenCount > 0 ? (
        <Badge variant="muted" className="shrink-0 px-1.5">
          +{hiddenCount}
        </Badge>
      ) : null}
    </div>
  );
}

function EnumBadge({ value, color }: { value: string; color: string }) {
  return (
    <Badge
      variant="outline"
      className="min-w-0 max-w-full shrink gap-1.5 truncate px-1.5"
      title={value}
    >
      <span
        className="h-2 w-2 shrink-0 rounded-full border border-border"
        style={{ backgroundColor: color, borderColor: color }}
        aria-hidden="true"
      />
      <span className="truncate">{value}</span>
    </Badge>
  );
}

function toEnumValues(value: unknown): string[] {
  if (value == null || value === "") {
    return [];
  }
  if (Array.isArray(value)) {
    return Array.from(
      new Set(
        value.flatMap((item) => {
          const enumValue = toEnumValue(item);
          return enumValue === null ? [] : [enumValue];
        }),
      ),
    );
  }

  const enumValue = toEnumValue(value);
  return enumValue === null ? [] : [enumValue];
}

function toEnumValue(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length === 0 ? null : trimmed;
  }
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }
  return null;
}

function getEnumColor(value: string): string {
  return ENUM_COLOR_PALETTE[hashString(value) % ENUM_COLOR_PALETTE.length];
}

function hashString(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}
