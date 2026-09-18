#!/usr/bin/env bash
set -euo pipefail

required=(
  DEPLOY_ENVIRONMENT KUBE_NAMESPACE BACKEND_IMAGE FRONTEND_IMAGE IMAGE_SHA
  APP_DOMAIN ACM_CERTIFICATE_ARN AWS_REGION SES_FROM_EMAIL SES_ROLE_ARN
  STORAGE_BACKEND PURGE_SCHEDULE REMINDER_SCHEDULE DIGEST_SCHEDULE
)
for name in "${required[@]}"; do
  if [ -z "${!name:-}" ]; then
    printf 'required deployment variable is empty: %s\n' "$name" >&2
    exit 2
  fi
done

case "$DEPLOY_ENVIRONMENT:$KUBE_NAMESPACE" in
  staging:minutes-staging|production:minutes-production) ;;
  *)
    printf 'environment and namespace must be staging:minutes-staging or production:minutes-production\n' >&2
    exit 2
    ;;
esac

if [[ ! "$IMAGE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'IMAGE_SHA must be a lowercase 40-character commit SHA\n' >&2
  exit 2
fi
if [[ ! "$BACKEND_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]] || [[ ! "$FRONTEND_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]; then
  printf 'BACKEND_IMAGE and FRONTEND_IMAGE must be immutable sha256 digest references\n' >&2
  exit 2
fi

export FRONTEND_SENTRY_DSN="${FRONTEND_SENTRY_DSN:-}"
export METRICS_ENABLED="${METRICS_ENABLED:-false}"
export TRUSTED_PROXY_IPS="${TRUSTED_PROXY_IPS:-}"
export RATE_LIMIT_CLEANUP_SCHEDULE="${RATE_LIMIT_CLEANUP_SCHEDULE:-*/5 * * * *}"
if [[ "$RATE_LIMIT_CLEANUP_SCHEDULE" == *$'\n'* ]]; then
  printf 'RATE_LIMIT_CLEANUP_SCHEDULE must be a five-field cron expression\n' >&2
  exit 2
fi
read -r -a rate_limit_schedule_fields <<< "$RATE_LIMIT_CLEANUP_SCHEDULE"
if [ "${#rate_limit_schedule_fields[@]}" -ne 5 ]; then
  printf 'RATE_LIMIT_CLEANUP_SCHEDULE must be a five-field cron expression\n' >&2
  exit 2
fi
for field in "${rate_limit_schedule_fields[@]}"; do
  if [[ ! "$field" =~ ^[[:alnum:]*/?,#LW-]+$ ]]; then
    printf 'RATE_LIMIT_CLEANUP_SCHEDULE contains an invalid cron field\n' >&2
    exit 2
  fi
done
export SENTRY_RELEASE="$IMAGE_SHA"
export MIGRATION_JOB_NAME="database-migrations-${IMAGE_SHA:0:12}"
export STORAGE_BACKEND

render_app() {
  if [ "$STORAGE_BACKEND" = local ]; then
    envsubst < deploy/app.yaml
    return
  fi
  if [ "$STORAGE_BACKEND" != s3 ]; then
    printf 'STORAGE_BACKEND must be local or s3\n' >&2
    exit 2
  fi
  for name in S3_BUCKET S3_PREFIX; do
    if [ -z "${!name:-}" ]; then
      printf 'required S3 deployment variable is empty: %s\n' "$name" >&2
      exit 2
    fi
  done
  command -v kubectl >/dev/null 2>&1 || {
    printf 'kubectl is required to render the S3 overlay\n' >&2
    exit 2
  }
  local temp_dir
  temp_dir="$(mktemp -d)"
  trap 'rm -rf "$temp_dir"' RETURN
  mkdir -p "$temp_dir/deploy" "$temp_dir/deploy-s3"
  cp deploy/kustomization.yaml "$temp_dir/deploy/kustomization.yaml"
  cp deploy-s3/kustomization.yaml "$temp_dir/deploy-s3/kustomization.yaml"
  envsubst < deploy/app.yaml > "$temp_dir/deploy/app.yaml"
  envsubst < deploy-s3/storage-s3-patch.yaml > "$temp_dir/deploy-s3/storage-s3-patch.yaml"
  kubectl kustomize "$temp_dir/deploy-s3"
}

render_file() {
  envsubst < "$1"
}

if [ "$#" -eq 1 ]; then
  output_dir="$1"
  mkdir -p "$output_dir"
  render_file deploy/namespace.yaml > "$output_dir/namespace.yaml"
  render_file deploy/service-account.yaml > "$output_dir/service-account.yaml"
  render_file deploy/migration-job.yaml > "$output_dir/migration-job.yaml"
  render_app > "$output_dir/app.yaml"
  render_file deploy/ingress.yaml > "$output_dir/ingress.yaml"
  exit 0
fi
if [ "$#" -ne 0 ]; then
  printf 'usage: %s [output-directory]\n' "$0" >&2
  exit 2
fi

for file in deploy/namespace.yaml deploy/service-account.yaml deploy/migration-job.yaml; do
  render_file "$file"
  printf '%s\n' '---'
done
render_app
printf '%s\n' '---'
render_file deploy/ingress.yaml
