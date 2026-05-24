import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";

export function NetworkBanner() {
  const [online, setOnline] = useState(() =>
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  useEffect(() => {
    function handleOnline() {
      setOnline(true);
    }

    function handleOffline() {
      setOnline(false);
    }

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  if (online) {
    return null;
  }

  return (
    <div className="flex min-h-10 items-center justify-center gap-2 border-b border-amber-300 bg-amber-100 px-4 py-2 text-sm font-medium text-amber-950">
      <WifiOff className="h-4 w-4" aria-hidden="true" />
      网络已断开，部分操作可能失败
    </div>
  );
}
