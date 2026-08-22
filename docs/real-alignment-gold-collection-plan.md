# Real trajectory alignment gold collection plan

This plan covers the evidence gap for the trajectory-alignment milestone. Synthetic regression
fixtures are not counted as real gold.

## Scope and source

- Owner: AgentLens project author.
- Target completion: before Session 3 alignment acceptance and before publishing any accuracy
  claim.
- Runner: a minimal ReAct-style agent with two frozen configurations.
- Tasks: 50 deterministic, local-only tool tasks using file search, structured lookup, arithmetic,
  and bounded retry scenarios. No user or production data is permitted.
- Runs: both configurations execute all 50 tasks, producing at least 100 runs and 50 paired
  variant comparisons. Additional repeated runs will bring the manually reviewed corpus to 100
  pairs.
- Variability: the task set intentionally includes harmless text rewrites, one retry insertion,
  repeated tool calls, argument changes, tool errors, and early termination.

The Session 1 synthetic quick/flagship fixtures are generated entirely by repository code from a
fixed seed, contain no external dataset or model output, and are distributed under the repository's
MIT license. Their injected-cause sidecar remains synthetic evidence and is never counted as real
gold.

## Provenance and licensing

The collection manifest will record the repository revision, task fixture revision, agent/model
configuration hashes, random seeds, collection date, and the model provider's data-use terms at
collection time. Only sanitized trajectories that the project author is permitted to redistribute
may be checked in. Model output containing credentials, personal data, absolute user paths, or
licensed source content will be rejected rather than redacted ad hoc.

## Annotation protocol

The project author will manually label 100 pairs with expected alignment operations, first
observed divergence, first action divergence, and FAD category. At least 50 pairs must come from
the collected agent runs; constructed edge cases remain marked separately. A second review pass
will resolve ambiguous indices and record the adjudication note without overwriting the original
label. The final manifest will keep real and constructed sources distinct.

## Acceptance evidence

Session 3 must report exact/degraded coverage, FAD category accuracy, FAD index accuracy within
one event, text-only FAD false-positive rate, and runtime using the frozen manifest. Until that
report exists, README and interview material must say that real alignment gold collection is
planned, not completed.
