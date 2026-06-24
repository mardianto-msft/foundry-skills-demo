# log_generator

Deterministic, dependency-free sample-log generator for the **foundry-skills**
prompt-agent demo. It produces realistic, time-ordered logs that each embed a
single, identifiable **root-cause signature**, plus a machine-readable
ground-truth file so the agent's diagnosis can be validated.

- **Standard library only** (`random`, `datetime`, `json`, `argparse`,
  `pathlib`, `os`) — no third-party dependencies.
- **Reproducible** via `--seed`.
- **Safe sample data** — no PII or secrets; client IPs use the RFC 5737
  documentation range (`192.0.2.x`) and hostnames are placeholders.

## Usage

Run as a module from the repository root:

```bash
python -m src.log_generator.generate --scenario all --seed 42 --out sample_logs
```

Or, if `src/` is on `PYTHONPATH`:

```bash
python -m log_generator.generate --scenario all --seed 42 --out sample_logs
```

Or directly:

```bash
python src/log_generator/generate.py --scenario web --seed 42 --out sample_logs
```

### Arguments

| Argument     | Default       | Description                                          |
|--------------|---------------|------------------------------------------------------|
| `--scenario` | `all`         | One of `web`, `k8s`, `mixed`, or `all`.              |
| `--seed`     | `42`          | Seed for deterministic output.                       |
| `--out`      | `sample_logs` | Output directory (created if missing).               |

## Output

For each scenario `<s>`, two files are written into `--out`:

- `sample_logs/<s>.log` — plain-text, time-ordered log lines (~80–150 lines).
- `sample_logs/<s>.expected.json` — ground truth:

  ```json
  {
    "scenario": "web",
    "root_cause": "…human-readable explanation…",
    "key_signatures": ["…", "…"]
  }
  ```

## Scenarios and planted root causes

### `web` — Database connection pool exhaustion
Healthy web/app-server traffic (`INFO`, request IDs, latencies) gives way to
HikariCP pool pressure and then exhaustion. The connection pool hits
`active=20, idle=0, waiting=12`, requests time out after 30s, and the failures
cascade into HTTP **500/503** responses and failing `/healthz` checks.
**Primary signature:** `HikariPool-1 - Connection is not available, request
timed out after 30000ms` / `PoolExhaustedException`.

### `k8s` — Container OOMKilled → CrashLoopBackOff
A pod's heap climbs past its `512Mi` limit; the kernel cgroup OOM killer
terminates the process (`exit_code=137`, `reason=OOMKilled`). Repeated kills
push the pod into **CrashLoopBackOff**, its readiness probe never passes, and
the Deployment falls below desired availability.
**Primary signature:** `Memory cgroup out of memory` / `reason=OOMKilled
exit_code=137` / `CrashLoopBackOff`.

### `mixed` — Expired upstream TLS certificate (amid noise)
A noisy feed of benign `INFO`/`WARN` messages from several services surrounds
one dominant fault: the upstream `payments.partner.example.invalid` TLS
certificate has **expired** (`notAfter=2026-06-15`). Outbound HTTPS calls fail
x509 verification, producing payment-capture failures, HTTP **502s**, and an
open circuit breaker.
**Primary signature:** `x509: certificate has expired or is not yet valid` /
`SSL_ERROR_EXPIRED_CERT_ALERT`.

## Determinism

The same `--seed` always yields byte-identical output. When generating `all`,
each scenario uses a per-scenario seed offset (`seed + index * 1000`) so the
feeds differ from one another while remaining fully reproducible.
