import * as React from "react";

import { cn } from "@/lib/utils";

export type CheckboxProps = Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "type"
> & {
  onCheckedChange?: (checked: boolean) => void;
};

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, onCheckedChange, onChange, ...props }, ref) => (
    <input
      ref={ref}
      type="checkbox"
      className={cn("h-4 w-4 rounded border-border accent-primary", className)}
      onChange={(event) => {
        onCheckedChange?.(event.currentTarget.checked);
        onChange?.(event);
      }}
      {...props}
    />
  ),
);
Checkbox.displayName = "Checkbox";

export { Checkbox };
