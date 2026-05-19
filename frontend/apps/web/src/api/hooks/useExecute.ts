import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import type { ExecuteRequest, ExecutionResult, QueryExecuteRequest } from "@/api/types";
import { queryHistoryKeys } from "@/api/hooks/useQueryHistory";
import { queryKeys } from "@/api/hooks/useQueries";
import { formatApiError } from "@/lib/formatApiError";
import type { ApiErrorBody } from "@/lib/formatApiError";

export type { ExecuteRequest, ExecutionResult, QueryExecuteRequest };

type ExecuteCallbacks = {
  onOdpsLogview?: (url: string) => void;
};

type ExecuteArgs = ExecuteCallbacks & {
  body: ExecuteRequest;
};

interface ExecuteSavedQueryArgs {
  queryId: number;
  payload?: QueryExecuteRequest;
  onOdpsLogview?: (url: string) => void;
}

type StreamEventName = "odps_logview" | "result" | "error";

type StreamEvent = {
  event: StreamEventName;
  data: unknown;
};

type OdpsLogviewEventData = {
  odps_logview_url: string;
};

export function useExecute() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ body, onOdpsLogview }: ExecuteArgs): Promise<ExecutionResult> => {
      return postExecutionStream("/api/v1/execute/stream", body, { onOdpsLogview });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.all }),
        queryClient.invalidateQueries({ queryKey: queryHistoryKeys.all }),
      ]);
    },
    onError: (err) => toast.error(formatApiError(err)),
  });
}

export function useExecuteQuery() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      queryId,
      payload = {},
      onOdpsLogview,
    }: ExecuteSavedQueryArgs): Promise<ExecutionResult> => {
      return postExecutionStream(`/api/v1/queries/${queryId}/execute/stream`, payload, {
        onOdpsLogview,
      });
    },
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.detail(result.query_id) }),
        queryClient.invalidateQueries({ queryKey: queryHistoryKeys.all }),
      ]);
    },
    onError: (err) => toast.error(formatApiError(err)),
  });
}

async function postExecutionStream(
  url: string,
  body: ExecuteRequest | QueryExecuteRequest,
  callbacks: ExecuteCallbacks,
): Promise<ExecutionResult> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errorBody = await readJsonError(response);
    throw { data: errorBody, error: errorBody, response };
  }

  if (response.body === null) {
    throw new Error("执行失败，服务器未返回流式响应");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ExecutionResult | null = null;
  let streamDone = false;

  while (!streamDone) {
    const { value, done } = await reader.read();
    streamDone = done;
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parsed = drainSseEvents(buffer);
    buffer = parsed.remaining;
    for (const event of parsed.events) {
      result = handleExecutionStreamEvent(event, callbacks, result);
    }
  }

  buffer += decoder.decode();
  const parsed = drainSseEvents(buffer);
  for (const event of parsed.events) {
    result = handleExecutionStreamEvent(event, callbacks, result);
  }

  if (result === null) {
    throw new Error("执行失败，服务器未返回查询结果");
  }
  return result;
}

async function readJsonError(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return {
      error: {
        code: "HTTP_ERROR",
        message: `执行失败，HTTP ${response.status}`,
      },
    };
  }
}

function drainSseEvents(buffer: string): { events: StreamEvent[]; remaining: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const remaining = blocks.pop() ?? "";
  return {
    events: blocks.map(parseSseEvent).filter((event): event is StreamEvent => event !== null),
    remaining,
  };
}

function parseSseEvent(block: string): StreamEvent | null {
  let eventName: StreamEventName | null = null;
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) {
      const rawEventName = line.slice("event: ".length);
      if (isStreamEventName(rawEventName)) {
        eventName = rawEventName;
      }
    } else if (line.startsWith("data: ")) {
      dataLines.push(line.slice("data: ".length));
    }
  }
  if (eventName === null || dataLines.length === 0) {
    return null;
  }
  return {
    event: eventName,
    data: JSON.parse(dataLines.join("\n")) as unknown,
  };
}

function handleExecutionStreamEvent(
  event: StreamEvent,
  callbacks: ExecuteCallbacks,
  currentResult: ExecutionResult | null,
): ExecutionResult | null {
  if (event.event === "odps_logview") {
    if (isOdpsLogviewEventData(event.data)) {
      callbacks.onOdpsLogview?.(event.data.odps_logview_url);
    }
    return currentResult;
  }
  if (event.event === "error") {
    throw event.data as ApiErrorBody;
  }
  return event.data as ExecutionResult;
}

function isStreamEventName(value: string): value is StreamEventName {
  return value === "odps_logview" || value === "result" || value === "error";
}

function isOdpsLogviewEventData(value: unknown): value is OdpsLogviewEventData {
  return (
    typeof value === "object" &&
    value !== null &&
    "odps_logview_url" in value &&
    typeof value.odps_logview_url === "string"
  );
}
