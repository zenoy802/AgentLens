import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { getApiError, type ApiErrorBody } from "@/lib/formatApiError";
import { suppressesGlobalErrorToast } from "@/api/mutationMeta";

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      showGlobalErrorToast(error, "请求失败", { suppressQueryNotFound: true });
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      if (suppressesGlobalErrorToast(mutation.meta)) {
        return;
      }
      showGlobalErrorToast(error, "操作失败");
    },
  }),
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10_000,
      gcTime: 5 * 60_000,
    },
    mutations: {
      retry: 0,
    },
  },
});

function showGlobalErrorToast(
  error: unknown,
  fallback: string,
  options?: { suppressQueryNotFound?: boolean },
) {
  const apiError = getApiError(error);
  if (apiError === null) {
    toast.error(fallback);
    return;
  }

  if (options?.suppressQueryNotFound === true && apiError.error.code === "QUERY_NOT_FOUND") {
    return;
  }

  toast.error(formatApiToastMessage(apiError));
}

function formatApiToastMessage(apiError: ApiErrorBody): string {
  if (apiError.error.code === "SELECTION_EXPIRED") {
    return "SELECTION_EXPIRED: 选择已过期，请重新选择行并复制 Agent Prompt";
  }
  if (apiError.error.code === "ANNOTATION_CLEAR_REQUIRES_FILTER") {
    return "ANNOTATION_CLEAR_REQUIRES_FILTER: 清理 annotation 需要 author、author_prefix、color 或 set 过滤条件";
  }

  return `${apiError.error.code}: ${apiError.error.message}`;
}
