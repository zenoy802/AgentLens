import { FormEvent, useEffect, useState } from "react";
import { Database } from "lucide-react";
import { toast } from "sonner";

import {
  useCreateConnection,
  useUpdateConnection,
} from "@/api/hooks/useConnections";
import type { ConnectionRead } from "@/api/hooks/useConnections";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatApiError } from "@/lib/formatApiError";

type ConnectionFormDialogProps = {
  open: boolean;
  connection: ConnectionRead | null;
  onOpenChange: (open: boolean) => void;
};

const DEFAULT_EXTRA_PARAMS = "{\n  \"charset\": \"utf8mb4\"\n}";

export function ConnectionFormDialog({
  open,
  connection,
  onOpenChange,
}: ConnectionFormDialogProps) {
  const createConnection = useCreateConnection();
  const updateConnection = useUpdateConnection();

  const isEditMode = connection !== null;

  const [name, setName] = useState("");
  const [dbType, setDbType] = useState("mysql");
  const [host, setHost] = useState("");
  const [port, setPort] = useState(3306);
  const [database, setDatabase] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [extraParamsText, setExtraParamsText] = useState(DEFAULT_EXTRA_PARAMS);
  const [defaultTimeout, setDefaultTimeout] = useState(30);
  const [defaultRowLimit, setDefaultRowLimit] = useState(10000);

  useEffect(() => {
    if (!open) return;

    if (connection !== null) {
      setName(connection.name);
      setDbType(connection.db_type);
      setHost(connection.host ?? "");
      setPort(connection.port ?? 3306);
      setDatabase(connection.database);
      setUsername(connection.username ?? "");
      setPassword("");
      setExtraParamsText(
        connection.extra_params
          ? JSON.stringify(connection.extra_params, null, 2)
          : DEFAULT_EXTRA_PARAMS,
      );
      setDefaultTimeout(connection.default_timeout);
      setDefaultRowLimit(connection.default_row_limit);
    } else {
      setName("");
      setDbType("mysql");
      setHost("");
      setPort(3306);
      setDatabase("");
      setUsername("");
      setPassword("");
      setExtraParamsText(DEFAULT_EXTRA_PARAMS);
      setDefaultTimeout(30);
      setDefaultRowLimit(10000);
    }
  }, [open, connection]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    let extraParams: Record<string, string | number | boolean | null> | undefined;
    const trimmedExtra = extraParamsText.trim();
    if (trimmedExtra.length > 0) {
      try {
        extraParams = JSON.parse(trimmedExtra) as Record<string, string | number | boolean | null>;
      } catch {
        toast.error("extra_params JSON 格式无效");
        return;
      }
    }

    const basePayload = {
      name: name.trim(),
      db_type: dbType as "mysql",
      host: host.trim() || null,
      port,
      database: database.trim(),
      username: username.trim() || null,
      extra_params: extraParams ?? null,
      default_timeout: defaultTimeout,
      default_row_limit: defaultRowLimit,
    };

    try {
      if (isEditMode) {
        const updatePayload: Record<string, unknown> = { ...basePayload };
        if (password.length > 0) {
          updatePayload["password"] = password;
        }
        await updateConnection.mutateAsync({
          id: connection.id,
          payload: updatePayload,
        });
        toast.success("连接已更新");
      } else {
        await createConnection.mutateAsync({
          ...basePayload,
          password: password || null,
        });
        toast.success("连接已创建");
      }
      onOpenChange(false);
    } catch (err) {
      toast.error(formatApiError(err));
    }
  }

  const isPending = createConnection.isPending || updateConnection.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5" aria-hidden="true" />
            <DialogTitle>{isEditMode ? "编辑连接" : "新建连接"}</DialogTitle>
          </div>
          <DialogDescription>
            {isEditMode ? "修改数据源连接配置" : "添加一个新的 MySQL 数据源连接"}
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={(event) => void handleSubmit(event)}
        >
          <label className="block text-sm font-medium">
            名称
            <input
              className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={200}
              placeholder="生产环境 MySQL"
            />
          </label>

          <label className="block text-sm font-medium">
            数据库类型
            <select
              className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
              value={dbType}
              onChange={(e) => setDbType(e.target.value)}
            >
              <option value="mysql">MySQL</option>
            </select>
          </label>

          <div className="grid grid-cols-3 gap-3">
            <label className="col-span-2 block text-sm font-medium">
              主机
              <input
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="localhost"
              />
            </label>
            <label className="block text-sm font-medium">
              端口
              <input
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                type="number"
                value={port}
                onChange={(e) => setPort(Number(e.target.value))}
                min={1}
                max={65535}
              />
            </label>
          </div>

          <label className="block text-sm font-medium">
            数据库
            <input
              className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
              value={database}
              onChange={(e) => setDatabase(e.target.value)}
              required
              maxLength={200}
              placeholder="agent_logs"
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm font-medium">
              用户名
              <input
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                maxLength={200}
              />
            </label>
            <label className="block text-sm font-medium">
              密码
              <input
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isEditMode ? "留空则不修改密码" : undefined}
                required={!isEditMode}
              />
            </label>
          </div>

          <label className="block text-sm font-medium">
            额外参数 (JSON)
            <textarea
              className="mt-1 min-h-24 w-full rounded-md border bg-background px-3 py-2 text-sm font-mono outline-none focus:ring-1 focus:ring-ring"
              value={extraParamsText}
              onChange={(e) => setExtraParamsText(e.target.value)}
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm font-medium">
              默认超时 (秒)
              <input
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                type="number"
                value={defaultTimeout}
                onChange={(e) => setDefaultTimeout(Number(e.target.value))}
                min={1}
                max={300}
              />
            </label>
            <label className="block text-sm font-medium">
              默认行数限制
              <input
                className="mt-1 h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                type="number"
                value={defaultRowLimit}
                onChange={(e) => setDefaultRowLimit(Number(e.target.value))}
                min={1}
                max={100000}
              />
            </label>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              取消
            </Button>
            <Button
              type="submit"
              disabled={isPending || name.trim().length === 0}
            >
              {isEditMode ? "保存" : "创建"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
