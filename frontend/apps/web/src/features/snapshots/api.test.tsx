import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import type { RunSnapshotRead } from "@/api/types";
import { useRunSnapshot } from "@/features/snapshots/api";
import { SnapshotFailureState } from "@/features/snapshots/routes/SnapshotsPage";

vi.mock("@/api/client", () => ({
  apiClient: { GET: vi.fn() },
}));

const BUILDING_SNAPSHOT: RunSnapshotRead = {
  schema_version: "run-snapshot-resource/v1",
  id: "00000000-0000-0000-0000-000000000001",
  name: "fixture",
  trace_contract_id: "00000000-0000-0000-0000-000000000002",
  trace_contract_version: 1,
  connection_id: 1,
  named_query_id: 2,
  named_query_name: "fixture-query",
  status: "building",
  input_fingerprint: "a".repeat(64),
  content_sha256: null,
  artifact_sha256: null,
  artifact_size_bytes: 0,
  source_row_count: 0,
  run_count: 0,
  progress_source_rows: 0,
  progress_runs: 0,
  pairing_key_field_coverage: null,
  build_policy: {
    version: "snapshot-build/v1",
    max_source_rows: 100,
    max_runs: 100,
    timeout_seconds: 30,
  },
  error: null,
  manifest: null,
  created_at: "2026-08-22T00:00:00Z",
  completed_at: null,
  deleted_at: null,
};

function PollingHarness() {
  const snapshot = useRunSnapshot(BUILDING_SNAPSHOT.id);
  return <div>{snapshot.data?.status ?? "loading"}</div>;
}

function TestProviders({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("snapshot polling and terminal states", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("cleans the polling interval when the consumer unmounts", async () => {
    vi.useFakeTimers();
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    const get = vi.mocked(apiClient.GET);
    get.mockResolvedValue({
      data: BUILDING_SNAPSHOT,
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    const view = render(<PollingHarness />, { wrapper: TestProviders });

    await act(async () => Promise.resolve());
    expect(get).toHaveBeenCalledTimes(1);
    act(() => vi.advanceTimersByTime(1_600));
    await act(async () => Promise.resolve());
    expect(get).toHaveBeenCalledTimes(2);

    view.unmount();
    act(() => vi.advanceTimersByTime(5_000));
    await act(async () => Promise.resolve());
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("renders failed and corrupted states with explicit text and code", async () => {
    const failed: RunSnapshotRead = {
      ...BUILDING_SNAPSHOT,
      status: "failed",
      error: { code: "SNAPSHOT_SOURCE_LIMIT_EXCEEDED", message: "Source limit exceeded." },
    };
    const { rerender } = render(<SnapshotFailureState snapshot={failed} />);
    expect(screen.getByText("Snapshot 构建失败")).toBeInTheDocument();
    expect(screen.getByText(/SNAPSHOT_SOURCE_LIMIT_EXCEEDED/)).toBeInTheDocument();

    rerender(
      <SnapshotFailureState
        snapshot={{
          ...failed,
          status: "corrupted",
          error: { code: "ARTIFACT_CORRUPTED", message: "Hash mismatch." },
        }}
      />,
    );
    await waitFor(() => expect(screen.getByText("Artifact 已损坏")).toBeInTheDocument());
  });
});
