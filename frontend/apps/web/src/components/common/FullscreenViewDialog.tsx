import { type ReactElement, type ReactNode } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type FullscreenViewDialogProps = {
  title: string;
  description?: string;
  trigger: ReactElement;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
};

export function FullscreenViewDialog({
  title,
  description,
  trigger,
  children,
  className,
  bodyClassName,
}: FullscreenViewDialogProps) {
  return (
    <Dialog>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent
        className={cn(
          "flex h-[calc(100vh-1rem)] max-h-none w-[calc(100vw-1rem)] max-w-none flex-col gap-0 p-0 sm:h-[calc(100vh-2rem)] sm:w-[calc(100vw-2rem)]",
          className,
        )}
      >
        <DialogHeader className="shrink-0 border-b px-4 py-3 pr-12">
          <DialogTitle className="text-base">{title}</DialogTitle>
          {description !== undefined ? (
            <DialogDescription>{description}</DialogDescription>
          ) : null}
        </DialogHeader>
        <div className={cn("min-h-0 flex-1 overflow-hidden bg-muted/20 p-3 sm:p-4", bodyClassName)}>
          {children}
        </div>
      </DialogContent>
    </Dialog>
  );
}
