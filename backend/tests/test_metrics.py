from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app as production_app
from app.metrics import install_metrics


METRICS_AUTH = {'Authorization': 'Bearer metrics-test-token'}
REPOSITORY = Path(__file__).resolve().parents[2]


def test_public_frontend_denies_metrics_and_backend_configuration_is_private():
    nginx = (REPOSITORY / 'frontend/nginx.conf').read_text()
    ingress = (REPOSITORY / 'deploy/ingress.yaml').read_text()
    ingress_manifest = yaml.safe_load(ingress)
    deployment = (REPOSITORY / 'deploy/app.yaml').read_text()
    compose = (REPOSITORY / 'compose.yaml').read_text()
    workflow = (REPOSITORY / '.github/workflows/ci.yaml').read_text()

    assert 'location = /metrics { access_log off; return 404; }' in nginx
    assert 'service: {name: frontend, port: {number: 80}}' in ingress
    backend_paths = [
        path['path']
        for path in ingress_manifest['spec']['rules'][0]['http']['paths']
        if path['backend']['service']['name'] == 'backend'
    ]
    assert backend_paths == ['/api']
    assert 'name: METRICS_ENABLED' in deployment
    assert 'key: metrics-token, optional: true' in deployment
    assert 'METRICS_ENABLED: ${METRICS_ENABLED:-false}' in compose
    assert 'METRICS_TOKEN: ${METRICS_TOKEN:-}' in compose
    assert "METRICS_ENABLED: ${{ vars.METRICS_ENABLED || 'false' }}" in workflow


def test_production_app_installs_disabled_metrics_endpoint():
    paths = {getattr(route, 'path', '') for route in production_app.routes}

    assert '/metrics' in paths
    assert TestClient(production_app).get('/metrics').status_code == 404


def test_metrics_endpoint_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv('METRICS_ENABLED', raising=False)
    monkeypatch.setenv('METRICS_TOKEN', 'configured-but-disabled')
    app = FastAPI()
    install_metrics(app)

    response = TestClient(app).get('/metrics', headers={'Authorization': 'Bearer configured-but-disabled'})

    assert response.status_code == 404


def test_enabled_metrics_endpoint_requires_configured_bearer_token():
    app = FastAPI()
    install_metrics(app, enabled=True, token='metrics-test-token')
    client = TestClient(app)

    missing = client.get('/metrics')
    wrong = client.get('/metrics', headers={'Authorization': 'Bearer wrong-token'})
    valid = client.get('/metrics', headers={'Authorization': 'Bearer metrics-test-token'})

    assert missing.status_code == 401
    assert missing.headers['www-authenticate'] == 'Bearer'
    assert wrong.status_code == 401
    assert valid.status_code == 200
    assert valid.headers['content-type'].startswith('text/plain; version=')

    unconfigured = FastAPI()
    install_metrics(unconfigured, enabled=True, token='')
    assert TestClient(unconfigured).get('/metrics', headers=METRICS_AUTH).status_code == 401


def test_request_metrics_use_bounded_route_status_and_method_labels_without_sensitive_data():
    app = FastAPI()

    @app.get('/items/{item_id}')
    def item(item_id: str):
        return {'id': item_id}

    @app.get('/failure')
    def failure():
        raise RuntimeError('private failure value')

    install_metrics(app, enabled=True, token='metrics-test-token')
    client = TestClient(app, raise_server_exceptions=False)

    assert client.get('/items/private-item-123?token=private-query').status_code == 200
    assert client.get('/unknown/private-id-one').status_code == 404
    assert client.get('/unknown/private-id-two').status_code == 404
    assert client.get('/failure').status_code == 500
    assert client.request('PRIVATE_SENTINEL_METHOD', '/items/private-item-456').status_code == 405
    exposition = client.get('/metrics', headers=METRICS_AUTH).text

    assert 'http_requests_total{method="GET",route="/items/{item_id}",status="200"} 1.0' in exposition
    assert 'http_requests_total{method="OTHER",route="/items/{item_id}",status="405"} 1.0' in exposition
    assert 'http_requests_total{method="GET",route="/unmatched",status="404"} 2.0' in exposition
    assert 'http_requests_total{method="GET",route="/failure",status="500"} 1.0' in exposition
    assert 'http_request_duration_seconds_count{method="GET",route="/items/{item_id}",status="200"} 1' in exposition
    assert 'http_request_duration_seconds_count{method="GET",route="/unmatched",status="404"} 2' in exposition
    assert 'http_request_duration_seconds_count{method="GET",route="/failure",status="500"} 1' in exposition
    assert 'private-item-123' not in exposition
    assert 'private-query' not in exposition
    assert 'private-id-one' not in exposition
    assert 'private-id-two' not in exposition
    assert 'private failure value' not in exposition
    assert 'PRIVATE_SENTINEL_METHOD' not in exposition


def test_health_and_metrics_routes_are_excluded_from_request_metrics():
    app = FastAPI()

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    install_metrics(app, enabled=True, token='metrics-test-token')
    client = TestClient(app)

    assert client.get('/api/health').status_code == 200
    first_scrape = client.get('/metrics', headers=METRICS_AUTH)
    second_scrape = client.get('/metrics', headers=METRICS_AUTH)

    assert first_scrape.status_code == 200
    assert second_scrape.status_code == 200
    assert 'route="/api/health"' not in second_scrape.text
    assert 'route="/metrics"' not in second_scrape.text


def test_concurrent_requests_are_counted_without_creating_identifier_labels():
    app = FastAPI()

    @app.get('/work/{work_id}')
    def work(work_id: str):
        return {'id': work_id}

    install_metrics(app, enabled=True, token='metrics-test-token')
    client = TestClient(app)

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(lambda item: client.get(f'/work/private-{item}'), range(64)))

    assert all(response.status_code == 200 for response in responses)
    exposition = client.get('/metrics', headers=METRICS_AUTH).text
    assert 'http_requests_total{method="GET",route="/work/{work_id}",status="200"} 64.0' in exposition
    assert 'http_request_duration_seconds_count{method="GET",route="/work/{work_id}",status="200"} 64' in exposition
    assert 'private-' not in exposition
