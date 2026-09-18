# Guardrail profiles for the fixed-user benchmark

## Benchmark identity

The target always runs as one mock customer, configured by
`SCENARIO_CUSTOMER_ID` and defaulting to `CUS-001`. This is scenario context from
the harness, not an identity asserted in an attacker prompt.

## Profile matrix

| Control | none | basic | strict |
|---|---:|---:|---:|
| Input injection filter | off | on | on |
| Full user-history inspection | off | on | on |
| Prompt hardening | off | on | on |
| Canary output check | off | on | on |
| Sensitive output filter | off | off | on |
| Tool authorization for the fixed customer | off | on | on |
| Retrieved-content trust label | off | on | on |
| Suspicious RAG chunk quarantine | off | off | on |
| Per-tool action policy | off | off | on |

`none` intentionally retains broken authorization so the red-team harness can
measure an unsafe baseline inside the sandbox. The base system prompt only
states the scenario identity; fixed-customer ownership instructions and the
untrusted-content rule are part of prompt hardening and therefore absent on
`none`. `basic` and `strict` perform deterministic authorization before a
customer-data or ticket tool executes; the LLM cannot grant itself or the
caller access by emitting another customer ID.

`strict` additionally applies per-tool call limits, requires explicit create-ticket
intent, binds ticket idempotency to the server request, and quarantines retrieved
chunks that contain deterministic prompt-injection indicators.

## Always-on RoE controls

The kill switch, allowlisted tools, request rate limit, total token budget, tool
loop limit, log redaction, and sandbox boundary are operational safety controls.
They remain enabled for every profile and must not be disabled to inflate attack
success rate.

The RAG document-management endpoints remain a benchmark control plane so the
harness can demonstrate indirect injection. They must only be exposed inside the
authorized sandbox. They are not production document-management APIs.

## Reproducible switching

Use `POST /config/defense-profile`, then verify `/health`. Every chat response
contains the effective `defense_profile`, guardrail actions, and a configuration
hash that includes the runtime profile and fixed scenario customer.
