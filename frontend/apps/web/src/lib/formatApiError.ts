export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    detail?: unknown;
  };
};

export function formatApiError(err: unknown): string {
  const apiError = getApiError(err);
  if (apiError !== null) {
    return `${apiError.error.code}: ${apiError.error.message}`;
  }

  if (err instanceof Error && err.message.length > 0) {
    return `UNKNOWN_ERROR: ${err.message}`;
  }

  return "UNKNOWN_ERROR: 未知错误";
}

export function getApiError(err: unknown): ApiErrorBody | null {
  if (isApiError(err)) {
    return err;
  }

  if (!isRecord(err)) {
    return null;
  }

  const nestedError = err.error;
  if (isApiError(nestedError)) {
    return nestedError;
  }

  const data = err.data;
  if (isApiError(data)) {
    return data;
  }

  return null;
}

export function isApiError(err: unknown): err is ApiErrorBody {
  if (!isRecord(err) || !isRecord(err.error)) {
    return false;
  }

  return typeof err.error.code === "string" && typeof err.error.message === "string";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
