import os
import time
from secrets import compare_digest

from fastapi import FastAPI, HTTPException, Request
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from starlette.responses import Response

from .observability import route_template


EXCLUDED_PATHS = {'/api/health', '/metrics'}
HTTP_METHODS = {'CONNECT', 'DELETE', 'GET', 'HEAD', 'OPTIONS', 'PATCH', 'POST', 'PUT', 'TRACE'}


class RequestMetricsMiddleware:
    def __init__(self, app, request_count: Counter, request_duration: Histogram):
        self.app = app
        self.request_count = request_count
        self.request_duration = request_duration

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') in EXCLUDED_PATHS:
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def send_with_status(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            method = scope['method']
            labels = {
                'method': method if method in HTTP_METHODS else 'OTHER',
                'route': route_template(scope),
                'status': str(status),
            }
            self.request_count.labels(**labels).inc()
            self.request_duration.labels(**labels).observe(time.perf_counter() - started)


def install_metrics(
    app: FastAPI,
    *,
    enabled: bool | None = None,
    token: str | None = None,
    registry: CollectorRegistry | None = None,
) -> CollectorRegistry:
    enabled = os.getenv('METRICS_ENABLED', 'false').strip().lower() == 'true' if enabled is None else enabled
    token = os.getenv('METRICS_TOKEN', '') if token is None else token
    registry = registry or CollectorRegistry()
    if enabled:
        labels = ('method', 'route', 'status')
        request_count = Counter(
            'http_requests_total',
            'Total HTTP requests completed by method, route template, and status.',
            labels,
            registry=registry,
        )
        request_duration = Histogram(
            'http_request_duration_seconds',
            'HTTP request latency by method, route template, and status.',
            labels,
            registry=registry,
        )
        app.add_middleware(RequestMetricsMiddleware, request_count=request_count, request_duration=request_duration)

    @app.get('/metrics', include_in_schema=False)
    async def scrape_metrics(request: Request):
        if not enabled:
            raise HTTPException(status_code=404)
        authorization = request.headers.get('authorization', '')
        supplied_token = authorization[7:] if authorization.startswith('Bearer ') else ''
        if not token or not supplied_token or not compare_digest(supplied_token, token):
            raise HTTPException(status_code=401, headers={'WWW-Authenticate': 'Bearer'})
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return registry
