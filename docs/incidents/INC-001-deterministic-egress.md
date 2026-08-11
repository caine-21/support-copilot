# INC-001: Provider egress reachable from deterministic challenge

- Severity: SEV-2 release blocker (synthetic environment)
- Status: Resolved locally
- Detected by: F13 hostile-input challenge, 2026-08-10

## Impact

One challenge request labeled provider-free reached the generic provider-capable normalization/retrieval path. No external support action occurred and no customer data was used, but the cost/privacy boundary was false and the hostile request was initially authorized too permissively.

## Root cause

`run_a1` disabled LLM normalization at its first normalization step, but its generic knowledge tool could still reach a provider-capable fallback. The public composition root had no explicit injection guard.

## Resolution

- Added a dedicated deterministic knowledge gateway that calls KB search with `allow_llm=False`.
- Added a deterministic prompt-injection pattern guard that returns `ESCALATE_L2` with `auto_reply_safe=false` before retrieval.
- Added F13 plus API regression coverage.

## Prevention

The failure matrix declares `provider_calls=synthetic_only`; demo/staging keeps provider calls disabled by default. Any future provider-free path must prove egress denial, not infer it from a flag name.
