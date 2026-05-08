import { CheckSquare, ChevronDown, Filter, RefreshCw } from "lucide-react";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Switch } from "@/components/ui/switch";

interface ComparisonToolbarProps {
  allKeys: string[];
  selectedKeys: string[];
  allRoles: string[];
  roleFilter: string[];
  syncScroll: boolean;
  maxSelection: number;
  onSelectionChange: (keys: string[]) => void;
  onRoleFilterChange: (roles: string[]) => void;
  onSyncScrollChange: (enabled: boolean) => void;
}

export function ComparisonToolbar({
  allKeys,
  selectedKeys,
  allRoles,
  roleFilter,
  syncScroll,
  maxSelection,
  onSelectionChange,
  onRoleFilterChange,
  onSyncScrollChange,
}: ComparisonToolbarProps) {
  const selectedKeySet = useMemo(() => new Set(selectedKeys), [selectedKeys]);
  const selectedRoleSet = useMemo(() => new Set(roleFilter), [roleFilter]);
  const selectedCount = allKeys.filter((key) => selectedKeySet.has(key)).length;
  const roleLabel =
    roleFilter.length === 0
      ? "无角色"
      : roleFilter.length === allRoles.length
        ? "全部角色"
        : roleFilter.join(", ");

  function selectAll() {
    onSelectionChange(allKeys.slice(0, maxSelection));
  }

  function invertSelection() {
    onSelectionChange(
      allKeys.filter((key) => !selectedKeySet.has(key)).slice(0, maxSelection),
    );
  }

  function toggleRole(role: string, checked: boolean) {
    const nextSet = new Set(roleFilter);
    if (checked) {
      nextSet.add(role);
    } else {
      nextSet.delete(role);
    }
    onRoleFilterChange(allRoles.filter((item) => nextSet.has(item)));
  }

  return (
    <div className="flex min-h-11 flex-wrap items-center gap-2 rounded-lg border bg-background px-3 py-2">
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5"
        disabled={allKeys.length === 0}
        title={`最多选择 ${maxSelection} 条 trajectory`}
        onClick={selectAll}
      >
        <CheckSquare className="h-3.5 w-3.5" aria-hidden="true" />
        全选
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="gap-1.5"
        disabled={allKeys.length === 0}
        title={`最多选择 ${maxSelection} 条 trajectory`}
        onClick={invertSelection}
      >
        <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
        反选
      </Button>
      <div className="mx-1 hidden h-5 w-px bg-border sm:block" />
      <div className="inline-flex h-8 items-center gap-2 rounded-md px-1 text-sm text-muted-foreground">
        <span>同步滚动</span>
        <Switch
          checked={syncScroll}
          aria-label="同步滚动"
          onCheckedChange={onSyncScrollChange}
        />
      </div>
      <div className="mx-1 hidden h-5 w-px bg-border sm:block" />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="max-w-[260px] gap-1.5"
            disabled={allRoles.length === 0}
            title={roleLabel}
          >
            <Filter className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="truncate">Role 过滤</span>
            <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-52">
          <DropdownMenuLabel>Role 过滤</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {allRoles.map((role) => (
            <DropdownMenuCheckboxItem
              key={role}
              checked={selectedRoleSet.has(role)}
              onSelect={(event) => event.preventDefault()}
              onCheckedChange={(checked) => toggleRole(role, checked === true)}
            >
              <span className="truncate" title={role}>
                {role}
              </span>
            </DropdownMenuCheckboxItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <div className="ml-auto text-sm text-muted-foreground">
        显示 <span className="font-medium text-foreground">{selectedCount}</span> /{" "}
        {allKeys.length} 条
      </div>
    </div>
  );
}
