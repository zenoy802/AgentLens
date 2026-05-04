const DEFAULT_FILENAME = "export";

export function parseFilenameFromHeader(
  contentDisposition: string | null,
  fallback = DEFAULT_FILENAME,
): string {
  if (contentDisposition === null) {
    return fallback;
  }

  const encodedFilename = getDispositionValue(contentDisposition, "filename*");
  if (encodedFilename !== null) {
    const normalized = stripQuotes(encodedFilename);
    const utf8Prefix = "UTF-8''";
    const encoded = normalized.toUpperCase().startsWith(utf8Prefix)
      ? normalized.slice(utf8Prefix.length)
      : normalized;
    try {
      return decodeURIComponent(encoded);
    } catch {
      return fallback;
    }
  }

  const plainFilename = getDispositionValue(contentDisposition, "filename");
  if (plainFilename !== null) {
    return stripQuotes(plainFilename) || fallback;
  }

  return fallback;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function getDispositionValue(header: string, key: "filename" | "filename*"): string | null {
  const parts = header.split(";").map((part) => part.trim());
  const prefix = `${key}=`;
  const match = parts.find((part) => part.toLowerCase().startsWith(prefix.toLowerCase()));
  return match === undefined ? null : match.slice(prefix.length);
}

function stripQuotes(value: string): string {
  const trimmed = value.trim();
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed.slice(1, -1).replace(/\\"/g, '"');
  }
  return trimmed;
}
