# Alerting

2026-09-17 · split from `04 Production Readiness Gaps.md`

**Status: code-complete. Live monitoring deployment and confirmed human firing/resolved receipts remain operator-gated.**

## Problem

Even though [07 - done - Health checks](./07%20-%20done%20-%20Health%20checks.md), [08 - done - Metrics](./08%20-%20done%20-%20Metrics.md), and [06 - done - Error tracking (Sentry)](./06%20-%20done%20-%20Error%20tracking%20%28Sentry%29.md) exist in code, collecting signals without notifying a human is only half the job.

## Requirements

- Alert when the five-minute 5xx ratio exceeds 5%, but only with at least 20 requests in the window and only after the condition persists for five minutes.
- Alert when a synthetic HTTP request to `/api/health` fails for two minutes.
- Alert separately when Prometheus cannot scrape the private backend target for two minutes; do not treat scrape `up` as application or database health.
- Group and repeat notifications at 30-minute intervals and send a resolved notification.
- Keep receiver credentials out of source control and require a real human-owned destination before claiming operational readiness.

## Implementation

`monitoring/alerts.yml` provides the three Prometheus rules. `monitoring/alerts.test.yml` deterministically covers firing, non-firing, low traffic, threshold delay, and recovery. CI validates both files with Prometheus 3.14.0 `promtool`.

`monitoring/prometheus.yml.template` wires the bearer-protected private backend metrics target, Alertmanager, and a Blackbox Exporter probe target. The template requires an operator-supplied absolute metrics-token file and approved health URL. `monitoring/blackbox.yml` requires an exact HTTP 200 and does not follow redirects.

`monitoring/alertmanager.yml` reads a human webhook URL from an out-of-band secret file, groups by alert name, uses 30-minute group/repeat intervals, and sends resolved notifications. CI validates it with Alertmanager 0.34.1 `amtool`. No recipient, credential, monitoring installation, or application deployment is created by this feature.

The [monitoring runbook](../../../monitoring/README.md) documents activation, validation, staging-only synthetic failures, recovery, resolved-delivery checks, and signal-specific triage. Local validation delivered both firing and resolved payloads to a loopback receiver; that proves configuration behavior only, not real human receipt.

## Operational gate

An operator must deploy and secure Prometheus, Alertmanager, and Blackbox Exporter; configure the private scrape token and approved health URL; provision a real human-owned receiver out of band; then run an approved staging firing/recovery drill. Code/config completion must not be reported as live production alerting until that evidence exists.
