import { ArrowDown, ArrowUp, EyeOff, Pin, Settings2 } from "lucide-react";

import type { FieldRender } from "@/api/types";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useQueryStore, type ColumnPinDirection } from "@/stores/queryStore";

interface ColumnHeaderMenuProps {
  columnName: string;
}

const CODE_LANGUAGES = ["sql", "python", "javascript", "typescript", "json", "plain"];
const TIMESTAMP_FORMATS = ["YYYY-MM-DD HH:mm:ss", "YYYY-MM-DD", "HH:mm:ss"];
const DEFAULT_FIELD_RENDER: FieldRender = { type: "text" };

export function ColumnHeaderMenu({ columnName }: ColumnHeaderMenuProps) {
  const render = useQueryStore((state) => state.fieldRenders[columnName] ?? DEFAULT_FIELD_RENDER);
  const tableConfig = useQueryStore((state) => state.tableConfig);
  const setFieldRender = useQueryStore((state) => state.setFieldRender);
  const toggleHiddenColumn = useQueryStore((state) => state.toggleHiddenColumn);
  const setColumnPin = useQueryStore((state) => state.setColumnPin);
  const setSort = useQueryStore((state) => state.setSort);

  const pinDirection = getPinDirection(tableConfig.pinned_columns[columnName], tableConfig.frozen_columns, columnName);
  const sortDirection = tableConfig.sort.find((item) => item.column === columnName)?.direction ?? null;

  function updateRender(nextRender: FieldRender) {
    setFieldRender(columnName, nextRender);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="ml-auto inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label={`配置 ${columnName} 列`}
          title="列配置"
          onClick={(event) => event.stopPropagation()}
        >
          <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-52" align="end" onClick={(event) => event.stopPropagation()}>
        <DropdownMenuLabel>渲染类型</DropdownMenuLabel>
        <RenderMenuItem active={render.type === "text"} onSelect={() => updateRender({ type: "text" })}>
          Text
        </RenderMenuItem>
        <RenderMenuItem
          active={render.type === "markdown"}
          onSelect={() => updateRender({ type: "markdown" })}
        >
          Markdown
        </RenderMenuItem>
        <RenderMenuItem
          active={render.type === "json"}
          onSelect={() => updateRender({ type: "json", collapsed: true })}
        >
          JSON
        </RenderMenuItem>
        <RenderMenuItem
          active={render.type === "enum"}
          onSelect={() => updateRender({ type: "enum", colors: {} })}
        >
          Enum
        </RenderMenuItem>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>Code</DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="w-40">
            {CODE_LANGUAGES.map((language) => (
              <RenderMenuItem
                key={language}
                active={render.type === "code" && render.language === language}
                onSelect={() => updateRender({ type: "code", language })}
              >
                {language}
              </RenderMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>Timestamp</DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="w-52">
            {TIMESTAMP_FORMATS.map((format) => (
              <RenderMenuItem
                key={format}
                active={render.type === "timestamp" && render.format === format}
                onSelect={() => updateRender({ type: "timestamp", format })}
              >
                {format}
              </RenderMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => toggleHiddenColumn(columnName)}>
          <EyeOff className="mr-2 h-3.5 w-3.5" aria-hidden="true" />
          隐藏列
        </DropdownMenuItem>

        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <Pin className="mr-2 h-3.5 w-3.5" aria-hidden="true" />
            冻结列
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="w-40">
            <PinMenuItem
              active={pinDirection === "left"}
              onSelect={() => setColumnPin(columnName, "left")}
            >
              Pin Left
            </PinMenuItem>
            <PinMenuItem
              active={pinDirection === "right"}
              onSelect={() => setColumnPin(columnName, "right")}
            >
              Pin Right
            </PinMenuItem>
            <PinMenuItem active={pinDirection === null} onSelect={() => setColumnPin(columnName, null)}>
              Unfreeze
            </PinMenuItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => setSort(columnName, "asc")}>
          <ArrowUp className="mr-2 h-3.5 w-3.5" aria-hidden="true" />
          Asc
          <ActiveMark active={sortDirection === "asc"} />
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setSort(columnName, "desc")}>
          <ArrowDown className="mr-2 h-3.5 w-3.5" aria-hidden="true" />
          Desc
          <ActiveMark active={sortDirection === "desc"} />
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setSort(columnName, null)}>Clear</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function RenderMenuItem({
  active,
  onSelect,
  children,
}: {
  active: boolean;
  onSelect: () => void;
  children: string;
}) {
  return (
    <DropdownMenuItem onSelect={onSelect}>
      {children}
      <ActiveMark active={active} />
    </DropdownMenuItem>
  );
}

function PinMenuItem({
  active,
  onSelect,
  children,
}: {
  active: boolean;
  onSelect: () => void;
  children: string;
}) {
  return (
    <DropdownMenuItem onSelect={onSelect}>
      {children}
      <ActiveMark active={active} />
    </DropdownMenuItem>
  );
}

function ActiveMark({ active }: { active: boolean }) {
  return (
    <span
      className={cn(
        "ml-auto h-1.5 w-1.5 rounded-full bg-foreground opacity-0",
        active && "opacity-100",
      )}
    />
  );
}

function getPinDirection(
  pinnedDirection: ColumnPinDirection | undefined,
  frozenColumns: string[],
  columnName: string,
): ColumnPinDirection | null {
  if (pinnedDirection !== undefined) {
    return pinnedDirection;
  }

  return frozenColumns.includes(columnName) ? "left" : null;
}
