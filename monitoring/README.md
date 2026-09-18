# Opt-in monitoring and alerting

These files are deployment templates, not an active monitoring service. The application stack does not install Prometheus, Alertmanager, or Blackbox Exporter, and alert delivery is not operational until an operator supplies infrastructure, secrets, a real health URL, and a human-owned receiver.

## Files and alert behavior

- `alerts.yml` defines three critical alerts.
  - `MinutesHigh5xxRate`: more than 5% 5xx responses over five minutes, only when at least 20 requests occurred in that window, sustained for five minutes.
  - `MinutesHealthProbeFailed`: Blackbox Exporter's real HTTP request to `/api/health` fails for two minutes. This exercises routing, the application, and the health endpoint's PostgreSQL check from the probe location.
  - `MinutesBackendScrapeDown`: Prometheus cannot scrape the private backend metrics target for two minutes. `up == 0` proves only scrape reachability; it is not a dependency-health check.
- `alerts.test.yml` provides deterministic firing, non-firing, low-traffic, delay, and recovery cases.
- `prometheus.yml.template` loads the rules, scrapes the bearer-protected private backend, sends alerts to Alertmanager, and sends the configured health URL through Blackbox Exporter.
- `blackbox.yml` requires an exact HTTP 200 without following redirects.
- `alertmanager.yml` groups alerts by name, waits 30 seconds before the first notification, uses 30-minute group and repeat intervals, and sends resolved notifications. Its webhook URL is read from `/etc/alertmanager/secrets/human-webhook-url`; no receiver credential or placeholder recipient is committed.

## Validate before activation

The CI versions are Prometheus 3.14.0, Blackbox Exporter 0.28.0, and Alertmanager 0.34.1. With those tools on `PATH`:

```sh
promtool check rules monitoring/alerts.yml
promtool test rules monitoring/alerts.test.yml
blackbox_exporter --config.file=monitoring/blackbox.yml --config.check
amtool check-config monitoring/alertmanager.yml
```

Render and validate the Prometheus template only in a protected working directory. `KUBE_NAMESPACE` must be exactly `minutes-staging` or `minutes-production`; `METRICS_TOKEN_FILE` must be an absolute path to a readable file containing the same token configured on that environment's backend; `APP_HEALTH_URL` must be the complete matching HTTPS URL ending in `/api/health`.

```sh
export METRICS_TOKEN_FILE=/etc/prometheus/secrets/metrics-token
export APP_HEALTH_URL=https://your-approved-host/api/health
export KUBE_NAMESPACE=minutes-staging
envsubst '${METRICS_TOKEN_FILE} ${APP_HEALTH_URL} ${KUBE_NAMESPACE}' \
  < monitoring/prometheus.yml.template \
  > /etc/prometheus/prometheus.yml
promtool check config /etc/prometheus/prometheus.yml
```

Before starting Alertmanager, provision `/etc/alertmanager/secrets/human-webhook-url` out of band with mode `0400` and a webhook owned by the on-call team. A secret manager or read-only secret volume is preferred. If email is required instead, replace the webhook receiver with an Alertmanager email receiver whose SMTP password is also supplied from a secret file. Never commit receiver URLs, mail credentials, or the metrics token.

Activation also requires all of the following:

1. Deploy Prometheus, Alertmanager, and Blackbox Exporter in an approved monitoring environment; this repository intentionally does not provision them.
2. Give Prometheus private network access to `backend.<namespace>.svc.cluster.local:8000` and Blackbox Exporter network access to that environment's approved application URL.
3. Set `METRICS_ENABLED=true` for the backend and provide the matching `metrics-token` key in `<namespace>-observability`. Keep the flag false until the private scraper and token are ready.
4. Mount `alerts.yml`, the rendered Prometheus configuration, `blackbox.yml`, the metrics token, `alertmanager.yml`, and the receiver secret at the paths expected by the chosen deployment.
5. Validate both configurations, reload or restart the services, and confirm all three rules are loaded before running a notification drill.

## Notification drill and recovery runbook

Run drills only in an isolated staging environment during an approved window. Do not generate intentional failures or 5xx traffic in production.

### Error-rate alert

1. Run `promtool test rules monitoring/alerts.test.yml`; this is the safe deterministic firing, low-traffic, exact-threshold, delay, and recovery check.
2. For an approved end-to-end staging drill, route synthetic traffic to a dedicated staging-only failure fixture so at least 20 requests occur in each five-minute window and more than 5% return 5xx. Never add a production debug route for this purpose.
3. Keep the condition true for five minutes and verify one grouped human notification after Alertmanager's group wait.
4. Stop the synthetic failures. Verify the expression becomes false within the next five-minute window and that the same receiver gets a resolved notification.
5. Record timestamps, the alert fingerprint, receiver, and scrubbed evidence. No note content, account identifier, token, URL query, or request body should appear.

### Health-probe alert

1. Confirm `probe_success{job="minutes-health"} == 1` and manually request the exact configured `/api/health` URL from the Blackbox Exporter network location.
2. In staging only, temporarily point the staging probe at a controlled endpoint returning non-200 or apply a reversible network block from Blackbox Exporter to the app. Do not alter the production health implementation or database.
3. After two minutes, verify `MinutesHealthProbeFailed` fires and reaches the human receiver.
4. Restore the original target or network path. Confirm `probe_success` returns to `1`, the alert clears on the next evaluation, and a resolved notification arrives.
5. If it fires unexpectedly, inspect Blackbox Exporter probe diagnostics, DNS/TLS/routing, then `/api/health` and PostgreSQL readiness. A healthy Prometheus scrape does not clear this alert.

### Scrape-target-down alert

1. Confirm `up{job="minutes-backend"} == 1` and that the private `/metrics` request succeeds with the token file.
2. In staging only, temporarily block Prometheus from the backend Service or stop the staging scrape target.
3. After two minutes, verify `MinutesBackendScrapeDown` fires and reaches the receiver.
4. Restore access, verify `up` returns to `1`, and confirm a resolved notification.
5. If only this alert fires, inspect the Service, network policy, bearer token, and metrics flag. Do not infer that `/api/health` or PostgreSQL is unhealthy unless the independent probe also fails.

Code/config completion is not proof that alerting is operational. Production readiness requires a separately approved live drill with confirmed human firing and resolved receipts.
