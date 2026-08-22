import { describe, expect, it } from "vitest";

import {
  buildContractDefinition,
  ContractDraftError,
  isSensitiveSampleColumn,
  redactSensitiveSampleValue,
} from "@/features/snapshots/contractDraft";
import { EMPTY_CONTRACT_DRAFT } from "@/features/snapshots/types";

describe("contract draft validation", () => {
  it("builds both discriminated layouts without handwritten API DTOs", () => {
    const runDefinition = buildContractDefinition(EMPTY_CONTRACT_DRAFT);
    const eventDefinition = buildContractDefinition({
      ...EMPTY_CONTRACT_DRAFT,
      sourceLayout: "event_rows",
    });

    expect(runDefinition.source_layout).toBe("run_rows");
    expect(eventDefinition.source_layout).toBe("event_rows");
  });

  it("rejects malformed and empty required outcome mappings", () => {
    expect(() =>
      buildContractDefinition({ ...EMPTY_CONTRACT_DRAFT, successValues: "not-json" }),
    ).toThrow(ContractDraftError);
    expect(() =>
      buildContractDefinition({ ...EMPTY_CONTRACT_DRAFT, failureValues: "[]" }),
    ).toThrow("Failure values cannot be empty");
  });

  it("removes known credential columns from source samples", () => {
    expect(isSensitiveSampleColumn("db_password_enc")).toBe(true);
    expect(isSensitiveSampleColumn("provider.api_key")).toBe(true);
    expect(isSensitiveSampleColumn("Authorization")).toBe(true);
    expect(isSensitiveSampleColumn("token_usage")).toBe(false);
    expect(
      redactSensitiveSampleValue({
        payload: { apiToken: "secret", answer: "safe" },
        messages: [{ content: "visible", private_key: "secret" }],
      }),
    ).toEqual({
      payload: { apiToken: "[REDACTED]", answer: "safe" },
      messages: [{ content: "visible", private_key: "[REDACTED]" }],
    });
  });
});
