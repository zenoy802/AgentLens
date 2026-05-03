import {
  Download,
  Edit,
  ExternalLink,
  MoreHorizontal,
  Save,
  Trash2,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import type { NamedQueryRead } from "@/api/hooks/useQueries";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type QueryActionsMenuProps = {
  query: NamedQueryRead;
  onEdit: (query: NamedQueryRead) => void;
  onPromote: (query: NamedQueryRead) => void;
  onDelete: (query: NamedQueryRead) => void;
};

export function QueryActionsMenu({
  query,
  onEdit,
  onPromote,
  onDelete,
}: QueryActionsMenuProps) {
  const navigate = useNavigate();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="h-8 w-8 p-0" aria-label="查询操作">
          <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-40">
        <DropdownMenuItem onSelect={() => navigate(`/query/${query.id}`)}>
          <ExternalLink className="mr-2 h-4 w-4" aria-hidden="true" />
          打开
        </DropdownMenuItem>
        {query.is_named ? (
          <DropdownMenuItem onSelect={() => onEdit(query)}>
            <Edit className="mr-2 h-4 w-4" aria-hidden="true" />
            编辑
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem onSelect={() => onPromote(query)}>
            <Save className="mr-2 h-4 w-4" aria-hidden="true" />
            Promote
          </DropdownMenuItem>
        )}
        <DropdownMenuItem disabled>
          <Download className="mr-2 h-4 w-4" aria-hidden="true" />
          导出 CSV
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-destructive focus:text-destructive"
          onSelect={() => onDelete(query)}
        >
          <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />
          删除
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
