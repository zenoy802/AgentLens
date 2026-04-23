import { useConnections } from "@/api/hooks/useConnections";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type ConnectionSelectProps = {
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
};

const EMPTY_CONNECTION_VALUE = "__none__";

export function ConnectionSelect({ value, onChange, disabled = false }: ConnectionSelectProps) {
  const connections = useConnections();
  const placeholder = connections.isLoading
    ? "加载连接..."
    : connections.isError
      ? "连接加载失败"
      : "选择连接";

  return (
    <label className="block min-w-[220px] text-sm font-medium">
      <span className="sr-only">连接</span>
      <Select
        value={value === null ? EMPTY_CONNECTION_VALUE : String(value)}
        onValueChange={(nextValue) => {
          onChange(nextValue === EMPTY_CONNECTION_VALUE ? null : Number(nextValue));
        }}
        disabled={disabled || connections.isLoading || connections.isError}
      >
        <SelectTrigger>
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value={EMPTY_CONNECTION_VALUE}>{placeholder}</SelectItem>
            {(connections.data?.items ?? []).map((connection) => (
              <SelectItem key={connection.id} value={String(connection.id)}>
                {connection.name} ({connection.db_type} {connection.host ?? "localhost"})
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </label>
  );
}
