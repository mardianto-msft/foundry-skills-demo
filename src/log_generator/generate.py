"""Deterministic sample-log generator for the foundry-skills demo.

Produces realistic, time-ordered plain-text logs for three scenarios, each
embedding exactly ONE dominant root-cause signature, plus a machine-readable
ground-truth file so a tester can validate an agent's diagnosis.

Standard library only (random, datetime, json, argparse, pathlib, os).

Usage::

    python -m src.log_generator.generate --scenario all --seed 42 --out sample_logs

Runs both as a module (``python -m src.log_generator.generate``) and directly
(``python src/log_generator/generate.py``).
"""

from __future__ import annotations

import argparse
import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

# Scenarios that map to a concrete log-builder. "all" is a meta-scenario.
SCENARIOS = ("web", "k8s", "mixed")

# RFC 5737 TEST-NET-1 documentation range — never routes anywhere real.
TEST_NET = "192.0.2."

# Placeholder hostnames / identifiers (no real PII or secrets).
WEB_HOSTS = ["web-app-01", "web-app-02", "web-app-03"]
SERVICES = ["checkout", "catalog", "orders", "payments", "search"]
USER_AGENTS = [
    "Mozilla/5.0 (compatible; DemoBot/1.0)",
    "curl/8.4.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
]
HTTP_PATHS = [
    "/api/v1/products",
    "/api/v1/cart",
    "/api/v1/orders",
    "/api/v1/checkout",
    "/healthz",
    "/api/v1/search",
]


def _rng(seed: int) -> random.Random:
    """Return a private, deterministic RNG instance for the given seed."""
    return random.Random(seed)


def _client_ip(rng: random.Random) -> str:
    """Return a documentation-range (RFC 5737) client IP."""
    return TEST_NET + str(rng.randint(2, 250))


def _req_id(rng: random.Random) -> str:
    """Return a short, opaque request id."""
    return "req-" + "".join(rng.choice("0123456789abcdef") for _ in range(12))


def _iso(ts: datetime) -> str:
    """Format a timestamp with millisecond precision and trailing Z (UTC)."""
    return ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


# --------------------------------------------------------------------------- #
# Scenario: web — database connection pool exhaustion -> cascading HTTP 500s.
# --------------------------------------------------------------------------- #
def build_web(seed: int):
    """Web/app-server logs. Root cause: DB connection pool exhaustion."""
    rng = _rng(seed)
    lines: list[str] = []
    ts = datetime(2026, 6, 17, 9, 0, 0, 0)

    def add(level: str, host: str, msg: str) -> None:
        nonlocal ts
        ts += timedelta(milliseconds=rng.randint(80, 900))
        lines.append(f"{_iso(ts)} {level:<5} [{host}] {msg}")

    # Phase 1: healthy baseline traffic.
    for _ in range(rng.randint(28, 36)):
        host = rng.choice(WEB_HOSTS)
        path = rng.choice(HTTP_PATHS)
        ip = _client_ip(rng)
        rid = _req_id(rng)
        latency = rng.randint(8, 95)
        add(
            "INFO",
            host,
            f'request_id={rid} {ip} "GET {path}" status=200 '
            f"latency_ms={latency} ua=\"{rng.choice(USER_AGENTS)}\"",
        )
        if rng.random() < 0.15:
            add(
                "DEBUG",
                host,
                f"request_id={rid} db.pool acquired conn "
                f"active={rng.randint(2, 9)}/20 idle={rng.randint(1, 8)}",
            )

    # Phase 2: pool pressure begins — the planted root cause.
    pool_host = "web-app-01"
    add(
        "WARN",
        pool_host,
        "db.pool HikariCP pool 'primary' near capacity active=19/20 "
        "idle=0 waiting=4",
    )
    add(
        "WARN",
        pool_host,
        "db.pool connection wait time rising avg_wait_ms=1850 threshold_ms=1000",
    )

    # Phase 3: exhaustion + cascading failures.
    for _ in range(rng.randint(30, 40)):
        host = rng.choice(WEB_HOSTS)
        svc = rng.choice(SERVICES)
        rid = _req_id(rng)
        ip = _client_ip(rng)
        roll = rng.random()
        if roll < 0.55:
            add(
                "ERROR",
                host,
                f"request_id={rid} service={svc} "
                "db.pool HikariPool-1 - Connection is not available, "
                "request timed out after 30000ms "
                "(total=20, active=20, idle=0, waiting=12)",
            )
            add(
                "ERROR",
                host,
                f'request_id={rid} {ip} "POST /api/v1/checkout" status=500 '
                "latency_ms=30007 error=\"PoolExhaustedException\"",
            )
        elif roll < 0.78:
            add(
                "ERROR",
                host,
                f"request_id={rid} service={svc} "
                "java.sql.SQLTransientConnectionException: "
                "HikariPool-1 - Connection is not available",
            )
        else:
            path = rng.choice(HTTP_PATHS)
            add(
                "WARN",
                host,
                f'request_id={rid} {ip} "GET {path}" status=503 '
                "latency_ms=30001 upstream_timeout=true",
            )

    add(
        "ERROR",
        "lb-gateway-01",
        "upstream web-app pool unhealthy: 0/3 backends passing health check "
        "/healthz (read timeout)",
    )
    add(
        "INFO",
        "oncall-bot",
        "ALERT fired: HighHttp5xxRate service=checkout value=63% "
        "for=5m runbook=db-pool-exhaustion",
    )

    root_cause = (
        "Database connection pool exhaustion (HikariCP 'primary' pool reached "
        "20/20 active connections with a growing wait queue), causing request "
        "timeouts that cascaded into HTTP 500/503 errors and failed health checks."
    )
    key_signatures = [
        "HikariPool-1 - Connection is not available, request timed out after 30000ms",
        "PoolExhaustedException",
        "active=20, idle=0, waiting=12",
        "SQLTransientConnectionException",
        "HighHttp5xxRate",
    ]
    return lines, root_cause, key_signatures


# --------------------------------------------------------------------------- #
# Scenario: k8s — OOMKilled -> CrashLoopBackOff -> readiness failures.
# --------------------------------------------------------------------------- #
def build_k8s(seed: int):
    """Kubernetes events + pod logs. Root cause: container OOMKilled."""
    rng = _rng(seed)
    lines: list[str] = []
    ts = datetime(2026, 6, 17, 14, 30, 0, 0)

    ns = "shop-prod"
    deploy = "orders-api"
    node = "aks-nodepool1-2271"
    pod = f"{deploy}-7c9f8b6d54-{''.join(rng.choice('abcde fghjkmnp'.replace(' ', '')) for _ in range(5))}"

    def add(source: str, level: str, msg: str) -> None:
        nonlocal ts
        ts += timedelta(milliseconds=rng.randint(120, 1400))
        lines.append(f"{_iso(ts)} {level:<5} [{source}] {msg}")

    # Phase 0: benign cluster baseline noise (other healthy pods on the node).
    other_pods = [f"catalog-api-5d{rng.randint(100, 999)}",
                  f"search-svc-6b{rng.randint(100, 999)}",
                  f"web-frontend-9a{rng.randint(100, 999)}"]
    for _ in range(rng.randint(34, 40)):
        op = rng.choice(other_pods)
        roll = rng.random()
        if roll < 0.7:
            add(op, "INFO", f"ns={ns} pod={op} "
                f"GET /healthz 200 latency_ms={rng.randint(1, 20)}")
        elif roll < 0.85:
            add("kubelet", "INFO", f"ns={ns} pod={op} "
                f"Liveness probe ok consecutive={rng.randint(1, 50)}")
        else:
            add("kube-controller", "INFO", f"ns={ns} pod={op} "
                f"metrics cpu_m={rng.randint(20, 180)} mem_mi={rng.randint(80, 300)}")

    # Phase 1: scheduling + startup.
    add("kubelet", "INFO", f"ns={ns} pod={pod} node={node} "
        "event=Scheduled Successfully assigned pod to node")
    add("kubelet", "INFO", f"ns={ns} pod={pod} event=Pulled "
        "Container image \"registry.example.invalid/orders-api:1.8.2\" already present")
    add("kubelet", "INFO", f"ns={ns} pod={pod} container=orders-api "
        "event=Created Created container")
    add("kubelet", "INFO", f"ns={ns} pod={pod} container=orders-api "
        "event=Started Started container")

    # Phase 2: app runs, memory climbing — the planted root cause.
    for pct in (41, 58, 72, 84, 93, 98):
        add(deploy, "INFO", f"pod={pod} heap_used_mb={int(pct * 5.12)} "
            f"limit_mb=512 utilization={pct}% gc_pause_ms={rng.randint(5, 40)}")
        if pct >= 84:
            add(deploy, "WARN", f"pod={pod} GC overhead high, "
                f"freed_mb={rng.randint(2, 12)} after_full_gc utilization={pct}%")

    # Phase 3: OOMKill + crash loop (repeated restarts).
    restarts = 0
    for backoff in (0, 10, 20, 40, 80, 160, 300):
        restarts += 1
        add("kernel", "ERROR", f"node={node} Memory cgroup out of memory: "
            f"Killed process (java) in pod {pod} total-vm:1843200kB anon-rss:524288kB")
        add("kubelet", "ERROR", f"ns={ns} pod={pod} container=orders-api "
            "event=OOMKilling Container exceeded memory limit "
            "reason=OOMKilled exit_code=137")
        add("kubelet", "WARN", f"ns={ns} pod={pod} container=orders-api "
            f"event=BackOff Back-off restarting failed container "
            f"reason=CrashLoopBackOff restart_count={restarts} backoff={backoff}s")
        add("kubelet", "WARN", f"ns={ns} pod={pod} "
            "event=Unhealthy Readiness probe failed: "
            "Get \"http://10.244.1.37:8080/ready\": dial tcp: connection refused")
        # A little benign cluster noise in between restarts.
        if rng.random() < 0.6:
            add("kube-controller", "INFO", f"ns={ns} deployment={deploy} "
                f"replicas desired=3 available={rng.randint(0, 2)} updated=3")

    add("kube-scheduler", "WARN", f"ns={ns} deployment={deploy} "
        "Deployment availability degraded: 1/3 pods Ready")
    add("alertmanager", "INFO", f"ALERT fired: PodCrashLooping ns={ns} pod={pod} "
        "reason=OOMKilled for=5m runbook=raise-memory-limit-or-fix-leak")

    root_cause = (
        "Container 'orders-api' exceeded its 512Mi memory limit and was "
        "OOMKilled (exit code 137). The repeated kills drove the pod into "
        "CrashLoopBackOff, so its readiness probe never passed and the "
        "Deployment dropped below desired availability."
    )
    key_signatures = [
        "Memory cgroup out of memory",
        "reason=OOMKilled exit_code=137",
        "CrashLoopBackOff",
        "Readiness probe failed",
        "exit_code=137",
    ]
    return lines, root_cause, key_signatures


# --------------------------------------------------------------------------- #
# Scenario: mixed — expired TLS certificate amid benign INFO/WARN noise.
# --------------------------------------------------------------------------- #
def build_mixed(seed: int):
    """Noisy multi-source feed. Root cause: expired upstream TLS certificate."""
    rng = _rng(seed)
    lines: list[str] = []
    ts = datetime(2026, 6, 17, 2, 15, 0, 0)

    sources = ["api-gateway", "auth-svc", "worker-03", "cron-runner",
               "cache-redis", "metrics-agent"]

    def add(source: str, level: str, msg: str) -> None:
        nonlocal ts
        ts += timedelta(milliseconds=rng.randint(150, 2200))
        lines.append(f"{_iso(ts)} {level:<5} [{source}] {msg}")

    benign_info = [
        "cache hit ratio=0.94 keys={k} evictions={e}",
        "scheduled job 'nightly-report' completed in {ms}ms rows={r}",
        "healthcheck ok deps=[db,cache,queue] latency_ms={ms}",
        "config reloaded watch=/etc/app/config.yaml generation={g}",
        "GET /metrics 200 scrape_duration_ms={ms}",
        "session refreshed user_id=usr-{u} ttl_s=3600",
    ]
    benign_warn = [
        "slow query detected duration_ms={ms} query='SELECT ... LIMIT 50'",
        "retrying transient publish to queue attempt={a}/3",
        "cache key 'catalog:{u}' near TTL expiry, refreshing",
        "deprecation: header 'X-Legacy-Auth' will be removed in v2",
    ]

    def noise() -> None:
        src = rng.choice(sources)
        if rng.random() < 0.78:
            tmpl = rng.choice(benign_info)
            add(src, "INFO", tmpl.format(
                k=rng.randint(1000, 9000), e=rng.randint(0, 20),
                ms=rng.randint(2, 240), r=rng.randint(50, 5000),
                g=rng.randint(10, 99), u=rng.randint(1000, 9999)))
        else:
            tmpl = rng.choice(benign_warn)
            add(src, "WARN", tmpl.format(
                ms=rng.randint(600, 3200), a=rng.randint(1, 3),
                u=rng.randint(1000, 9999)))

    # Phase 1: pure benign noise.
    for _ in range(rng.randint(40, 48)):
        noise()

    # Phase 2: the planted root cause appears — upstream TLS cert expired.
    upstream = "payments.partner.example.invalid"
    add("api-gateway", "ERROR", f"upstream={upstream} TLS handshake failed: "
        "x509: certificate has expired or is not yet valid: "
        "current time 2026-06-17T02:16:44Z is after 2026-06-15T00:00:00Z")
    add("api-gateway", "ERROR", f"upstream={upstream} "
        "SSL_ERROR_EXPIRED_CERT_ALERT depth=0 "
        "subject=\"CN=payments.partner.example.invalid\" notAfter=2026-06-15")

    # Phase 3: secondary symptoms interleaved with continuing noise.
    for _ in range(rng.randint(42, 52)):
        roll = rng.random()
        if roll < 0.42:
            add("payments-client", "ERROR", f"call to {upstream}/charge failed "
                "error=\"certificate verify failed (cert expired)\" "
                f"request_id={_req_id(rng)} retry=false")
        elif roll < 0.60:
            add("worker-03", "ERROR", "payment capture job failed "
                "reason=upstream_tls_error status=502 "
                f"order_id=ord-{rng.randint(10000, 99999)}")
        elif roll < 0.72:
            add("api-gateway", "WARN", f"circuit breaker OPEN for upstream={upstream} "
                f"failures={rng.randint(20, 80)} window=60s")
        else:
            noise()

    add("alertmanager", "INFO", "ALERT fired: UpstreamTLSCertExpired "
        f"upstream={upstream} notAfter=2026-06-15 "
        "runbook=rotate-partner-tls-cert")

    root_cause = (
        "The TLS certificate for upstream 'payments.partner.example.invalid' "
        "expired (notAfter 2026-06-15), so all outbound HTTPS calls failed "
        "x509 verification. This caused payment-capture failures, HTTP 502s, "
        "and an open circuit breaker — while unrelated INFO/WARN noise continued."
    )
    key_signatures = [
        "x509: certificate has expired or is not yet valid",
        "SSL_ERROR_EXPIRED_CERT_ALERT",
        "certificate verify failed (cert expired)",
        "notAfter=2026-06-15",
        "UpstreamTLSCertExpired",
    ]
    return lines, root_cause, key_signatures


BUILDERS = {
    "web": build_web,
    "k8s": build_k8s,
    "mixed": build_mixed,
}


def write_scenario(scenario: str, seed: int, out_dir: Path) -> int:
    """Generate one scenario and write its .log and .expected.json files.

    Returns the number of log lines written.
    """
    builder = BUILDERS[scenario]
    lines, root_cause, key_signatures = builder(seed)

    out_dir.mkdir(parents=True, exist_ok=True)

    log_path = out_dir / f"{scenario}.log"
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    expected = {
        "scenario": scenario,
        "root_cause": root_cause,
        "key_signatures": key_signatures,
    }
    expected_path = out_dir / f"{scenario}.expected.json"
    expected_path.write_text(
        json.dumps(expected, indent=2) + "\n", encoding="utf-8"
    )
    return len(lines)


def generate(scenario: str, seed: int, out_dir: Path) -> dict[str, int]:
    """Generate one or all scenarios. Returns {scenario: line_count}."""
    targets = list(SCENARIOS) if scenario == "all" else [scenario]
    results: dict[str, int] = {}
    for index, name in enumerate(targets):
        # Offset the seed per scenario so each feed differs but stays
        # deterministic for a given top-level seed.
        results[name] = write_scenario(name, seed + index * 1000, out_dir)
    return results


def parse_args(argv=None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="log_generator.generate",
        description="Generate deterministic sample logs with planted "
                    "root-cause signatures for the foundry-skills demo.",
    )
    parser.add_argument(
        "--scenario",
        choices=("web", "k8s", "mixed", "all"),
        default="all",
        help="Which scenario(s) to generate (default: all).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed for deterministic, reproducible output (default: 42).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("sample_logs"),
        help="Output directory (default: sample_logs).",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """Entry point. Returns a process exit code."""
    args = parse_args(argv)
    results = generate(args.scenario, args.seed, args.out)

    out_abs = os.path.abspath(args.out)
    print(f"Generated sample logs (seed={args.seed}) -> {out_abs}")
    for name, count in results.items():
        print(f"  {name:<6} {count:>4} lines  "
              f"({name}.log, {name}.expected.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
