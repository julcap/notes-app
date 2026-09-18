import json

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.transport import Transport

from app.error_tracking import initialize_error_tracking
from app.observability import request_id
from app.main import app


class RecordingTransport(Transport):
    def __init__(self):
        super().__init__()
        self.events = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            event = item.get_event()
            if event is not None:
                self.events.append(event)


def test_error_tracking_is_disabled_without_a_dsn(monkeypatch):
    monkeypatch.delenv('SENTRY_DSN', raising=False)
    initialized = []

    assert initialize_error_tracking(init=initialized.append) is False
    assert initialized == []


def test_configured_backend_captures_scrubbed_exception_with_stack(monkeypatch):
    monkeypatch.setenv('SENTRY_DSN', 'https://public@example.invalid/1')
    monkeypatch.setenv('SENTRY_ENVIRONMENT', 'test')
    monkeypatch.setenv('SENTRY_RELEASE', 'minutes@abc123')
    transport = RecordingTransport()
    token = request_id.set('request-safe-123')
    try:
        assert initialize_error_tracking(transport=transport) is True
        try:
            raise RuntimeError('EXCEPTION_SECRET_SENTINEL private@example.com note-987')
        except RuntimeError as error:
            sentry_sdk.capture_exception(error)
        sentry_sdk.flush(timeout=2)
    finally:
        request_id.reset(token)
        sentry_sdk.init(dsn=None)

    assert len(transport.events) == 1
    event = transport.events[0]
    exception = event['exception']['values'][0]
    assert exception['type'] == 'RuntimeError'
    assert 'value' not in exception
    assert exception['stacktrace']['frames'][-1]['function'] == 'test_configured_backend_captures_scrubbed_exception_with_stack'
    assert event['tags'] == {'request_id': 'request-safe-123'}
    assert event['environment'] == 'test'
    assert event['release'] == 'minutes@abc123'
    assert 'EXCEPTION_SECRET_SENTINEL' not in json.dumps(event)
    assert 'private@example.com' not in json.dumps(event)
    assert 'note-987' not in json.dumps(event)


def test_backend_initialization_disables_pii_tracing_profiles_logs_and_scrubs_complete_payload(monkeypatch):
    monkeypatch.setenv('SENTRY_DSN', 'https://public@example.invalid/1')
    monkeypatch.setenv('SENTRY_ENVIRONMENT', 'production')
    monkeypatch.setenv('SENTRY_RELEASE', 'minutes@release-safe')
    configured = {}

    def fake_init(**options):
        configured.update(options)

    assert initialize_error_tracking(init=fake_init) is True
    assert configured['send_default_pii'] is False
    assert configured['traces_sample_rate'] == 0.0
    assert configured['profiles_sample_rate'] == 0.0
    assert configured['enable_logs'] is False
    assert any(isinstance(integration, FastApiIntegration) for integration in configured['integrations'])

    sentinel = 'PRIVATE_SENTINEL private@example.com 192.0.2.1 note-123'
    token = request_id.set('correlation-safe')
    try:
        event = configured['before_send'](
            {
                'event_id': 'a' * 32,
                'timestamp': '2026-09-18T00:00:00Z',
                'platform': 'python',
                'level': 'error',
                'environment': 'production',
                'release': 'minutes@release-safe',
                'request': {
                    'url': f'https://app.example/api/notes/note-123?token={sentinel}#fragment',
                    'headers': {'authorization': sentinel, 'cookie': sentinel},
                    'cookies': {'refresh_token': sentinel},
                    'data': {'content': sentinel},
                    'query_string': sentinel,
                    'env': {'REMOTE_ADDR': '192.0.2.1'},
                },
                'user': {'email': 'private@example.com', 'ip_address': '192.0.2.1'},
                'contexts': {'trace': {'trace_id': sentinel}},
                'extra': {'note_content': sentinel},
                'exception': {'values': [{
                    'type': 'RuntimeError',
                    'value': sentinel,
                    'stacktrace': {'frames': [{
                        'filename': f'/srv/app/main.py?secret={sentinel}#fragment',
                        'function': 'failure',
                        'lineno': 42,
                        'vars': {'secret': sentinel},
                        'context_line': sentinel,
                    }]},
                }]},
                'breadcrumbs': {'values': [{
                    'category': 'http',
                    'type': 'http',
                    'level': 'info',
                    'message': sentinel,
                    'data': {'url': sentinel, 'Authorization': sentinel},
                }]},
            },
            {},
        )
    finally:
        request_id.reset(token)

    serialized = json.dumps(event)
    assert sentinel not in serialized
    assert 'private@example.com' not in serialized
    assert '192.0.2.1' not in serialized
    assert 'note-123' not in serialized
    assert set(event) == {
        'event_id', 'timestamp', 'platform', 'level', 'environment', 'release',
        'exception', 'breadcrumbs', 'tags'
    }
    assert event['exception']['values'][0] == {
        'type': 'RuntimeError',
        'stacktrace': {'frames': [{'filename': 'main.py', 'function': 'failure', 'lineno': 42}]},
    }
    assert event['breadcrumbs']['values'] == [{'category': 'http', 'type': 'http', 'level': 'info'}]
    assert event['tags'] == {'request_id': 'correlation-safe'}
    assert configured['before_breadcrumb']({
        'category': 'http', 'type': 'http', 'level': 'info', 'message': sentinel, 'data': {'url': sentinel}
    }, {}) == {'category': 'http', 'type': 'http', 'level': 'info'}

    poisoned_metadata = configured['before_send']({
        'event_id': sentinel,
        'timestamp': sentinel,
        'platform': sentinel,
        'level': sentinel,
        'environment': 'production',
        'release': 'minutes@release-safe',
    }, {})
    assert sentinel not in json.dumps(poisoned_metadata)
    assert poisoned_metadata == {'environment': 'production', 'release': 'minutes@release-safe'}


def test_application_has_no_permanent_crash_endpoint():
    paths = {getattr(route, 'path', '') for route in app.routes}
    assert not any('crash' in path or 'sentry-debug' in path for path in paths)
