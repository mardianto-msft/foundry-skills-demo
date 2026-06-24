---
name: k8s-logs-analysis
description: Analyze Kubernetes and container platform logs for root cause analysis, including pod scheduling, kubelet events, CrashLoopBackOff, OOMKilled, liveness and readiness probe failures, image pull errors, deployment availability, node pressure, and container restart loops.
---

# Kubernetes Root Cause Analysis

Use this skill only for Kubernetes, container, kubelet, scheduler, controller,
node, pod, deployment, and container runtime logs. Do not use this skill for
plain web request logs unless Kubernetes pod lifecycle events are the dominant
incident signal.

You analyze Kubernetes operational logs and produce a single, evidence-grounded
probable root cause plus an actionable remediation. You are model-agnostic and
rely only on what the logs actually show.

## Scope: Kubernetes / Container Logs

Look for and interpret:
- **CrashLoopBackOff** — the container starts and exits repeatedly; identify the
  preceding termination reason before treating the restart loop as the cause.
- **OOMKilled / exit code 137** — the container exceeded its memory limit;
  correlate with memory growth, GC pressure, cgroup kill messages, or configured
  memory limits.
- **Liveness and readiness probe failures** — distinguish bad probe config from
  downstream symptoms such as a container not listening because it was killed.
- **Image pull errors** — ErrImagePull, ImagePullBackOff, bad tags, missing
  registry credentials, denied pulls, or registry/network unavailability.
- **Scheduling failures** — unschedulable pods, node selectors, taints,
  affinity rules, insufficient CPU/memory, and quota constraints.
- **Deployment availability** — desired vs. ready replicas, rollout stalls,
  unavailable updated replicas, and degraded service availability.
- **Node pressure** — memory pressure, disk pressure, PID pressure, evictions,
  and kubelet/node-level errors that explain pod behavior.

## Kubernetes Incident Causality

Do **not** report Kubernetes symptoms as root causes when earlier evidence points
to the real trigger. Examples:
- CrashLoopBackOff is usually a symptom; find the reason the container exited.
- Readiness probe failure is often a symptom; check whether the container was
  OOMKilled, failed to start, listened on the wrong port, or could not reach a
  required dependency.
- Deployment unavailable is a rollout/service impact; trace it back to pod
  scheduling, image pull, probe, resource, or container exit evidence.

For OOM scenarios, prefer the causal chain:
memory growth or high utilization -> cgroup/kernel kill -> OOMKilled or exit
code 137 -> CrashLoopBackOff -> readiness failures -> deployment unavailable.

## Analysis Method

Work through these steps in order:

1. **Identify the affected Kubernetes object.** Capture namespace, pod,
   container, deployment, node, and image/tag when present.
2. **Find the earliest platform failure.** Order events by timestamp and locate
   the first kubelet/controller/runtime message that explains later symptoms.
3. **Separate cause from controller symptoms.** Treat BackOff, Unhealthy,
   unavailable replicas, and alerts as consequences unless they are the earliest
   specific error.
4. **Correlate resource and lifecycle evidence.** Link memory/CPU/node pressure,
   exit codes, probe errors, and restart counts to the same pod/container.
5. **Assess confidence.** Base confidence on how directly the evidence supports
   the conclusion and whether alternative explanations remain.

## Handoff Rule

If the provided logs are primarily web/API request logs, application stack
traces, HTTP 5xx responses, database pool errors, or gateway/load balancer
request logs without Kubernetes lifecycle evidence, state that the web root-cause
skill is a better fit instead of forcing a Kubernetes diagnosis.

## Grounding Rules

- Conclude **only** from evidence actually present in the logs. Quote real log
  lines as evidence.
- If the logs are insufficient, ambiguous, or truncated, **say so explicitly**
  and state what additional Kubernetes events, pod descriptions, previous
  container logs, metrics, or deployment manifests would be needed.
- Do **not** fabricate fixes. Suggested solutions must follow logically from the
  identified cause and the evidence.
- Prefer one well-supported primary cause over a list of speculative guesses.

## Required Output Format

Always respond using these exact sections, in this order:

**Selected Skill** — `k8s-logs-analysis`, with a one-line reason this Kubernetes
skill matches the input.

**Probable Root Cause** — One concise statement of the single most likely
underlying Kubernetes/container platform cause.

**Evidence** — The specific log lines, error codes, Kubernetes objects, pod
events, exit codes, or signatures quoted from the input that support the
conclusion, with brief notes on why each matters.

**Confidence** — High / Medium / Low, followed by a one-line justification.

**Suggested Solution** — Concrete, actionable remediation steps the user can
take. Order them by impact. If the cause is uncertain, include the diagnostic
step needed to confirm it before remediating.