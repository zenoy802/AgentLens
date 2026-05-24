import { useEffect } from "react";

export function useBeforeUnloadGuard(
  when: boolean,
) {
  useEffect(() => {
    if (!when) {
      return undefined;
    }

    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
      return "";
    };

    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [when]);
}
