export function RawCell({ value }: { value: unknown }) {
  const str = stringifyRawValue(value);
  return (
    <div className="truncate" title={str}>
      {str}
    </div>
  );
}

export function stringifyRawValue(value: unknown): string {
  try {
    const json = JSON.stringify(value, bigintReplacer);
    return json ?? String(value);
  } catch {
    return safeString(value);
  }
}

function bigintReplacer(_key: string, value: unknown): unknown {
  return typeof value === "bigint" ? value.toString() : value;
}

function safeString(value: unknown): string {
  try {
    return String(value);
  } catch {
    return "[unserializable value]";
  }
}
