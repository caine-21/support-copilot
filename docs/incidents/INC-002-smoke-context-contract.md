# INC-002: Positive smoke fixture used the wrong customer-context shape

- Severity: SEV-3 verification defect
- Status: Contained; known runtime limitation documented
- Detected by: local staging HTTP smoke, 2026-08-10

## Impact

The first positive smoke used flat customer fields while the Beta contract requires an `as_of` plus `fields` envelope. The workflow returned `UNKNOWN` after a validation error. After correcting the fixture, the canonical A1 facade still chose conservative `ESCALATE_L1`; it did not perform an unsafe automatic action.

## Root cause

The smoke test invented a simplified context shape instead of reusing the frozen Customer Context Beta contract. The current `run_a1` facade also has a conservative context-projection mismatch that prevents this password-reset example from proving positive AUTO eligibility.

## Resolution

- The smoke fixture now uses the frozen context envelope.
- The safety assertion is explicit: an AUTO result must have `grounding_safe=true`; a human escalation is safe but is not called an AUTO success.
- The L1 result is retained as a known limitation rather than weakening authorization.

## Follow-up

Create a separate, reviewer-approved issue before changing A1 context projection. That change touches the authorization claim and must rerun Customer Context Beta plus the full regression suite.
