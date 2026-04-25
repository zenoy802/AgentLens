import * as React from "react";

import { cn } from "@/lib/utils";

const Form = React.forwardRef<HTMLFormElement, React.FormHTMLAttributes<HTMLFormElement>>(
  ({ className, ...props }, ref) => {
    return <form ref={ref} noValidate className={cn("space-y-4", className)} {...props} />;
  },
);
Form.displayName = "Form";

export { Form };
