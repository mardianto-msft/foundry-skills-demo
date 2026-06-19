---
name: web-logs-analysis
description: Analyze web and application server logs for root cause analysis, including HTTP 5xx errors, request timeouts, unhandled exceptions, database connection failures, connection pool exhaustion, upstream dependency failures, and load balancer health symptoms.
---

# Web Log Root Cause Analysis

Use this skill only for web, API, gateway, load balancer, and application server
logs. Do not use this skill for Kubernetes control-plane events, pod lifecycle
events, kubelet messages, container image pull failures, OOMKilled pod events,
CrashLoopBackOff pod events, or readiness/liveness probe failures unless they are
only downstream symptoms inside an otherwise web/application log incident.

You analyze raw web logs and produce a single, evidence-grounded probable root
cause plus an actionable remediation. You are model-agnostic and rely only on
what the logs actually show.

## Scope: Web / Application Server Logs

Look for and interpret:
- **HTTP 5xx errors** (500, 502, 503, 504) — distinguish app crashes (500) from
  upstream/gateway failures (502/504) and overload/unavailable (503).
- **Request timeouts** — slow downstream calls, thread/connection pool
  exhaustion, deadlocks.
- **Unhandled exceptions / stack traces** — read the topmost application frame
  (not just the framework frame) to locate the failing code path.
- **Database connection errors** — connection refused, pool exhausted,
  authentication failures, timeouts, "too many connections".
- **Connection pool saturation** — active connections at limit, no idle
  connections, long waiters, HikariCP or equivalent pool timeout messages.
- **Load balancer health symptoms** — unhealthy upstream pool, backend read
  timeouts, and health endpoint failures caused by web application saturation.

## Web Incident Causality

When multiple overlapping failures appear, do **not** report them all as equal.
Find the **PRIMARY root cause** — the earliest, upstream failure that triggers
the cascade — and explain downstream symptoms as consequences. Example: a DB
connection pool failure (cause) leads to request timeouts (symptom), HTTP 500s
or 503s (symptom), failed health checks (symptom), and load balancer backend
removal (symptom).

## Analysis Method

Work through these steps in order:

1. **Identify the dominant error signature.** Scan for the most frequent and
   most severe recurring error pattern. Note its exact message/code.
2. **Correlate timestamps and sequence.** Order events chronologically. The
   *first* failure in a causal chain is usually closer to the root cause than
   later, repeated symptoms.
3. **Distinguish symptom vs. cause.** Ask "what triggered this?" for each error.
   A 503 or a restarting pod is usually a symptom; trace back to the originating
   failure (e.g., dependency down, resource limit, bad config).
4. **Assess confidence.** Base confidence on how directly the evidence supports
   the conclusion and whether alternative explanations remain.

## Handoff Rule

If the provided logs are primarily Kubernetes lifecycle events, kubelet events,
pod scheduling/restart events, OOMKilled messages, CrashLoopBackOff messages,
probe configuration failures, or image pull errors, state that the Kubernetes
root-cause skill is a better fit instead of forcing a web-log diagnosis.

## Grounding Rules

- Conclude **only** from evidence actually present in the logs. Quote real log
  lines as evidence.
- If the logs are insufficient, ambiguous, or truncated, **say so explicitly**
  and state what additional logs/data would be needed. Do not invent a cause.
- Do **not** fabricate fixes. Suggested solutions must follow logically from the
  identified cause and the evidence.
- Prefer one well-supported primary cause over a list of speculative guesses.

## Required Output Format

Always respond using these exact sections, in this order:

**Selected Skill** — `web-logs-analysis`, with a one-line reason this web-log skill
matches the input.

**Probable Root Cause** — One concise statement of the single most likely
underlying cause.

**Evidence** — The specific log lines, error codes, or signatures (quoted from
the input) that support the conclusion, with brief notes on why each matters.

**Confidence** — High / Medium / Low, followed by a one-line justification
(e.g., "High — single clear error signature directly precedes all downstream
failures").

**Suggested Solution** — Concrete, actionable remediation steps the user can
take. Order them by impact. If the cause is uncertain, include the diagnostic
step needed to confirm it before remediating.