import { Settings2 } from "lucide-react";

import type { TrajectoryConfig } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useQueryStore } from "@/stores/queryStore";

const REQUIRED_EMPTY = "__agentlens_required_empty__";
const OPTIONAL_EMPTY = "__agentlens_optional_empty__";

const EMPTY_CONFIG: TrajectoryConfig = {
  group_by: "",
  role_column: "",
  content_column: "",
  tool_calls_column: null,
  order_by: null,
  order_direction: "asc",
};

export function TrajectoryConfigPanel() {
  const columns = useQueryStore((state) => state.columns);
  const trajectoryConfig = useQueryStore((state) => state.trajectoryConfig);
  const setTrajectoryConfig = useQueryStore((state) => state.setTrajectoryConfig);
  const columnNames = columns.map((column) => column.name);
  const activeConfig = trajectoryConfig ?? EMPTY_CONFIG;

  function updateConfig(patch: Partial<TrajectoryConfig>) {
    setTrajectoryConfig({
      ...EMPTY_CONFIG,
      ...trajectoryConfig,
      ...patch,
    });
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" title="配置 Trajectory 聚合字段">
          <Settings2 className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
          Trajectory 配置
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Trajectory 配置</DialogTitle>
          <DialogDescription>
            选择字段后点击“确定”返回查询页；字段变更会标记当前视图为未保存，需要再点击“保存视图”才会持久化。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 md:grid-cols-2">
          <ColumnSelect
            label="Group By"
            value={activeConfig.group_by}
            columns={columnNames}
            required
            onChange={(value) => updateConfig({ group_by: value ?? "" })}
          />
          <ColumnSelect
            label="Role Column"
            value={activeConfig.role_column}
            columns={columnNames}
            required
            onChange={(value) => updateConfig({ role_column: value ?? "" })}
          />
          <ColumnSelect
            label="Content Column"
            value={activeConfig.content_column}
            columns={columnNames}
            required
            onChange={(value) => updateConfig({ content_column: value ?? "" })}
          />
          <ColumnSelect
            label="Tool Calls Column"
            value={activeConfig.tool_calls_column ?? null}
            columns={columnNames}
            onChange={(value) => updateConfig({ tool_calls_column: value })}
          />
          <ColumnSelect
            label="Order By"
            value={activeConfig.order_by ?? null}
            columns={columnNames}
            onChange={(value) => updateConfig({ order_by: value })}
          />
          <div className="space-y-2">
            <Label>Order Direction</Label>
            <Select
              value={activeConfig.order_direction}
              onValueChange={(value) => {
                if (value === "asc" || value === "desc") {
                  updateConfig({ order_direction: value });
                }
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="asc">asc</SelectItem>
                <SelectItem value="desc">desc</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setTrajectoryConfig(null)}
          >
            清空配置
          </Button>
          <DialogClose asChild>
            <Button type="button">确定</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ColumnSelectProps {
  label: string;
  value: string | null;
  columns: string[];
  required?: boolean;
  onChange: (value: string | null) => void;
}

function ColumnSelect({
  label,
  value,
  columns,
  required = false,
  onChange,
}: ColumnSelectProps) {
  const emptyValue = required ? REQUIRED_EMPTY : OPTIONAL_EMPTY;
  const selectValue = value === null || value === "" ? emptyValue : value;
  const hasColumns = columns.length > 0;

  return (
    <div className="space-y-2">
      <Label>
        {label}
        {required ? <span className="ml-1 text-destructive">*</span> : null}
      </Label>
      <Select
        value={selectValue}
        disabled={!hasColumns}
        onValueChange={(nextValue) => {
          if (nextValue === emptyValue) {
            onChange(required ? "" : null);
            return;
          }
          onChange(nextValue);
        }}
      >
        <SelectTrigger>
          <SelectValue placeholder={hasColumns ? "选择列" : "先执行查询"} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={emptyValue}>
            {required ? "未选择" : "不使用"}
          </SelectItem>
          {columns.map((column) => (
            <SelectItem key={column} value={column}>
              {column}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
