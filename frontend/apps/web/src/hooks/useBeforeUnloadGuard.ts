import { useEffect } from "react";

export function useBeforeUnloadGuard(
  when: boolean,
  message = "有未保存的变更，确定离开吗？",
) {
  useEffect(() => {
    if (!when) {
      return undefined;
    }

    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = message;
      return message;
    };

    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [when, message]);
}
