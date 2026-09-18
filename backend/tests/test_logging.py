import asyncio
import json
import logging
import re
from io import StringIO

import pyotp
from fastapi.testclient import TestClient

from app import auth
from app.main import app
from app.observability import configure_logging, log_event, request_id
from conftest import register, signed_in, token
from test_auth import csrf, enable_totp


def emitted_logs(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def capture_logs():
    stream = StringIO()
    configure_logging(stream)
    return stream


def test_json_logs_are_parseable_scrub_third_party_messages_and_isolate_contexts():
    stream = StringIO()
    access_logger = logging.getLogger('uvicorn.access')
    access_logger.disabled = True
    configure_logging(stream)
    assert access_logger.disabled is True
    access_logger.disabled = False
    secret = 'LOG_SECRET_SENTINEL'

    access_logger.info(
        'GET /api/notes?token=%s email=%s',
        secret,
        'private@example.com',
        extra={
            'event': 'auth_event',
            'auth_event': 'login',
            'outcome': 'success',
            'method': 'POST',
            'route': '/api/notes/{note_id}',
            'status': 200,
            'stack': [{'file': secret, 'line': 1, 'function': secret}],
        },
    )

    async def emit(bound_request_id):
        token = request_id.set(bound_request_id)
        try:
            await asyncio.sleep(0)
            log_event(logging.getLogger('app.test'), logging.INFO, 'context_probe')
        finally:
            request_id.reset(token)

    async def concurrently():
        await asyncio.gather(emit('request-a'), emit('request-b'))

    asyncio.run(concurrently())
    records = emitted_logs(stream)

    assert all(record['timestamp'].endswith('Z') for record in records)
    assert all(record['level'] in {'info', 'warning', 'error', 'critical'} for record in records)
    assert records[0]['event'] == 'dependency_log'
    assert set(records[0]) == {'timestamp', 'level', 'logger', 'event', 'request_id'}
    assert {record['request_id'] for record in records if record['event'] == 'context_probe'} == {
        'request-a',
        'request-b',
    }
    serialized = stream.getvalue()
    assert secret not in serialized
    assert 'private@example.com' not in serialized
    assert '/api/notes?' not in serialized


def test_request_id_is_validated_echoed_and_never_logs_raw_request_data(raw):
    stream = capture_logs()
    valid_request_id = 'client-request_123:trace'
    valid = raw.get('/api/auth/providers', headers={'x-request-id': valid_request_id})
    assert valid.headers['x-request-id'] == valid_request_id

    sentinel = 'bad request id PRIVATE_EMAIL@example.com?token=TOKEN_SENTINEL'
    invalid = raw.get('/api/auth/providers?email=PRIVATE_EMAIL@example.com&token=TOKEN_SENTINEL', headers={'x-request-id': sentinel})
    replacement = invalid.headers['x-request-id']
    traced = raw.request('TRACE', '/api/auth/providers', headers={'x-request-id': 'trace-request'})

    assert replacement != sentinel
    assert re.fullmatch(r'[0-9a-f]{32}', replacement)
    assert traced.status_code == 405
    assert traced.headers['x-request-id'] == 'trace-request'
    records = emitted_logs(stream)
    request_records = [record for record in records if record['event'] == 'request_completed']
    assert {record['request_id'] for record in request_records} == {valid_request_id, replacement, 'trace-request'}
    assert all(record['route'] == '/api/auth/providers' for record in request_records)
    assert {(record['method'], record['status']) for record in request_records} == {('GET', 200), ('TRACE', 405)}
    assert 'PRIVATE_EMAIL@example.com' not in stream.getvalue()
    assert 'TOKEN_SENTINEL' not in stream.getvalue()
    assert 'bad request id' not in stream.getvalue()


def test_unhandled_errors_log_safe_type_and_stack_without_exception_value():
    stream = capture_logs()

    def failure():
        raise RuntimeError('EXCEPTION_SECRET_SENTINEL')

    original_routes = list(app.router.routes)
    app.add_api_route('/api/test-only-logging-failure', failure)
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            '/api/test-only-logging-failure', headers={'x-request-id': 'failed-request'}
        )
    finally:
        app.router.routes[:] = original_routes
    records = emitted_logs(stream)
    error = next(record for record in records if record['event'] == 'unhandled_error')
    request_record = next(record for record in records if record['event'] == 'request_completed')

    assert response.status_code == 500
    assert response.headers['x-request-id'] == 'failed-request'
    assert error['error_type'] == 'RuntimeError'
    assert error['stack'][-1]['function'] == 'failure'
    assert request_record['status'] == 500
    assert request_record['level'] == 'error'
    assert 'EXCEPTION_SECRET_SENTINEL' not in stream.getvalue()


def test_auth_events_cover_password_oauth_2fa_and_reset_without_sensitive_values(raw, monkeypatch):
    stream = capture_logs()
    email = 'AUTH_EMAIL_SENTINEL@example.com'
    password = 'AUTH_PASSWORD_SENTINEL1'
    registered = raw.post('/api/auth/register', json={
        'email': email,
        'password': password,
        'password_confirmation': password,
    })
    assert registered.status_code == 201
    verification = token(raw)
    assert raw.post('/api/auth/verify-email', json={'token': verification}).status_code == 200

    assert raw.post('/api/auth/login', json={'email': email, 'password': 'WRONG_PASSWORD_SENTINEL'}).status_code == 401
    assert raw.post('/api/auth/login', json={'email': email, 'password': password}).status_code == 200
    assert raw.post('/api/auth/forgot-password', json={'email': email}).status_code == 200

    raw.headers['Authorization'] = 'Bearer ' + registered.json()['access_token']
    assert raw.post('/api/auth/verify-email', json={'token': verification}).status_code == 400
    signed_in(raw, 'second@example.com')
    secret, _ = enable_totp(raw)
    assert raw.post('/api/auth/2fa/disable', json={'password': 'SafePassword123'}, headers=csrf(raw)).status_code == 200
    secret, _ = enable_totp(raw)
    raw.headers.pop('Authorization')
    challenge = raw.post('/api/auth/login', json={'email': 'second@example.com', 'password': 'SafePassword123'}).json()['mfa_token']
    assert raw.post('/api/auth/login/2fa', json={'mfa_token': challenge, 'code': pyotp.TOTP(secret).now()}).status_code == 200

    class FakeGoogleClient:
        async def authorize_access_token(self, request):
            return {'userinfo': {
                'sub': 'OAUTH_SUBJECT_SENTINEL',
                'email': 'oauth@example.com',
                'email_verified': True,
                'name': 'OAuth user',
            }}

    monkeypatch.setattr(auth.oauth, 'create_client', lambda provider: FakeGoogleClient())
    oauth_response = raw.get('/api/auth/google/callback', follow_redirects=False)
    assert oauth_response.status_code == 303
    assert oauth_response.headers['location'].endswith('/auth/callback')

    records = emitted_logs(stream)
    auth_events = [
        (record['auth_event'], record['outcome'], record.get('auth_method'))
        for record in records
        if record['event'] == 'auth_event'
    ]
    assert ('login', 'failure', 'password') in auth_events
    assert ('login', 'success', 'password') in auth_events
    assert ('password_reset_requested', 'accepted', None) in auth_events
    assert ('2fa_enabled', 'success', None) in auth_events
    assert ('2fa_disabled', 'success', None) in auth_events
    assert ('login', 'success', 'two_factor') in auth_events
    assert ('login', 'success', 'oauth') in auth_events

    serialized = stream.getvalue()
    for sensitive in (
        email,
        password,
        'WRONG_PASSWORD_SENTINEL',
        verification,
        secret,
        'OAUTH_SUBJECT_SENTINEL',
    ):
        assert sensitive not in serialized
