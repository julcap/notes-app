#!/bin/sh
set -eu

sentry_dsn=${FRONTEND_SENTRY_DSN:-}
environment=${SENTRY_ENVIRONMENT:-}
release=${SENTRY_RELEASE:-}
runtime_config_path=${RUNTIME_CONFIG_PATH:-/tmp/runtime-config.js}

if [ -n "$sentry_dsn" ] && ! printf '%s' "$sentry_dsn" | grep -Eq '^https://[A-Za-z0-9._~-]+@[A-Za-z0-9.-]+(:[0-9]+)?/[A-Za-z0-9._~/-]+$'; then
    sentry_dsn=''
fi
if [ -n "$environment" ] && ! printf '%s' "$environment" | grep -Eq '^[A-Za-z0-9._:@/+=-]{1,128}$'; then
    environment=''
fi
if [ -n "$release" ] && ! printf '%s' "$release" | grep -Eq '^[A-Za-z0-9._:@/+=-]{1,128}$'; then
    release=''
fi

umask 022
printf 'window.__MINUTES_CONFIG__ = Object.freeze({sentryDsn:"%s",environment:"%s",release:"%s"});\n' \
    "$sentry_dsn" "$environment" "$release" > "$runtime_config_path"
