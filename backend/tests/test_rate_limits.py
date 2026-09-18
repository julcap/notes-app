from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from ipaddress import ip_network
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app import rate_limits
from app.auth.models import RateBucket
from app.database import SessionLocal
from app.jobs import cleanup_rate_limits
from app.main import app
from conftest import HEADERS, signed_in
from test_api import note


def clear_rate_buckets():
    with SessionLocal() as session:
        session.execute(delete(RateBucket))
        session.commit()


def test_authenticated_limit_is_shared_by_sessions_and_isolated_by_user(raw, monkeypatch):
    first = signed_in(raw, 'first@example.com')
    second_session = raw.post(
        '/api/auth/login',
        json={'email': 'first@example.com', 'password': 'SafePassword123'},
    ).json()
    second = signed_in(raw, 'second@example.com')
    clear_rate_buckets()
    monkeypatch.setattr(rate_limits, 'AUTHENTICATED_LIMIT', 2)

    with TestClient(app, headers={**HEADERS, 'Authorization': f"Bearer {first['access_token']}"}) as first_client, TestClient(
        app,
        headers={**HEADERS, 'Authorization': f"Bearer {second_session['access_token']}"},
    ) as same_user_client:
        assert first_client.get('/api/auth/me').status_code == 200
        assert same_user_client.get('/api/auth/me').status_code == 200
        assert first_client.get('/api/auth/me').status_code == 429

    raw.headers['Authorization'] = f"Bearer {second['access_token']}"
    assert raw.get('/api/auth/me').status_code == 200


def test_unauthenticated_limits_are_per_transport_ip_and_ignore_forged_forwarding(raw, monkeypatch):
    clear_rate_buckets()
    monkeypatch.setattr(rate_limits, 'UNAUTHENTICATED_LIMIT', 1)

    with TestClient(app, headers=HEADERS, client=('198.51.100.10', 50000)) as first, TestClient(
        app,
        headers=HEADERS,
        client=('198.51.100.11', 50000),
    ) as second:
        assert first.get('/api/auth/providers', headers={'X-Forwarded-For': '203.0.113.1'}).status_code == 200
        assert second.get('/api/auth/providers').status_code == 200
        response = first.get(
            '/api/auth/providers',
            headers={'Authorization': 'Bearer malformed', 'X-Forwarded-For': '203.0.113.2'},
        )

    assert response.status_code == 429


def test_trusted_proxy_uses_rightmost_untrusted_address(raw, monkeypatch):
    clear_rate_buckets()
    monkeypatch.setattr(rate_limits, 'UNAUTHENTICATED_LIMIT', 1)
    monkeypatch.setattr(rate_limits, 'TRUSTED_PROXY_NETWORKS', (ip_network('10.0.0.0/8'),))

    with TestClient(app, headers=HEADERS, client=('10.0.0.5', 50000)) as proxy:
        assert proxy.get(
            '/api/auth/providers',
            headers={'X-Forwarded-For': '203.0.113.9, 198.51.100.1, 10.0.0.4'},
        ).status_code == 200
        assert proxy.get(
            '/api/auth/providers',
            headers={'X-Forwarded-For': '192.0.2.9, 198.51.100.1, 10.0.0.4'},
        ).status_code == 429
        assert proxy.get(
            '/api/auth/providers',
            headers={'X-Forwarded-For': '203.0.113.9, 198.51.100.2, 10.0.0.4'},
        ).status_code == 200
        assert proxy.get(
            '/api/auth/providers',
            headers={'X-Forwarded-For': '10.0.0.7, 10.0.0.4'},
        ).status_code == 200
        assert proxy.get(
            '/api/auth/providers',
            headers={'X-Forwarded-For': '10.0.0.8, 10.0.0.4'},
        ).status_code == 429
        clear_rate_buckets()
        assert proxy.get(
            '/api/auth/providers',
            headers={'X-Forwarded-For': 'malformed'},
        ).status_code == 200
        assert proxy.get(
            '/api/auth/providers',
            headers={'X-Forwarded-For': 'still-malformed'},
        ).status_code == 429


def test_universal_trusted_proxy_ranges_are_rejected():
    for value in ('0.0.0.0/0', '::/0', '10.0.0.0/8,0.0.0.0/0'):
        with pytest.raises(ValueError, match='universal'):
            rate_limits.parse_trusted_proxy_networks(value)


def test_retry_after_tracks_remaining_window_and_expired_bucket_resets(raw, monkeypatch):
    current_time = datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(rate_limits, 'UNAUTHENTICATED_LIMIT', 1)
    monkeypatch.setattr(rate_limits, 'GENERAL_WINDOW_SECONDS', 60)
    monkeypatch.setattr(rate_limits, 'rate_limit_clock', lambda: current_time)
    clear_rate_buckets()

    assert raw.get('/api/auth/providers').status_code == 200
    current_time += timedelta(seconds=10)
    response = raw.get('/api/auth/providers')
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '50'

    current_time += timedelta(seconds=50)
    assert raw.get('/api/auth/providers').status_code == 200


def test_upload_and_export_have_additional_per_user_limits(client, monkeypatch):
    monkeypatch.setattr(rate_limits, 'AUTHENTICATED_LIMIT', 100)
    monkeypatch.setattr(rate_limits, 'UPLOAD_LIMIT', 1)
    monkeypatch.setattr(rate_limits, 'EXPORT_LIMIT', 1)
    meeting = note(client)
    clear_rate_buckets()

    upload_path = f"/api/notes/{meeting['id']}/attachments"
    assert client.post(upload_path, files={'file': ('first.txt', b'first')}).status_code == 201
    assert client.post(upload_path, files={'file': ('second.txt', b'second')}).status_code == 429

    export_path = f"/api/notes/{meeting['id']}/export"
    assert client.get(export_path, params={'format': 'md'}).status_code == 200
    assert client.get(export_path, params={'format': 'md'}).status_code == 429


def test_standalone_action_items_consume_general_limit(client, monkeypatch):
    meeting = note(client)
    item = client.post(
        f"/api/notes/{meeting['id']}/action-items",
        json={'text': 'Follow up'},
    ).json()
    clear_rate_buckets()
    monkeypatch.setattr(rate_limits, 'AUTHENTICATED_LIMIT', 1)

    assert client.patch(f"/api/action-items/{item['id']}", json={'done': True}).status_code == 200
    assert client.delete(f"/api/action-items/{item['id']}").status_code == 429


def test_simultaneous_increments_are_atomic(raw):
    clear_rate_buckets()
    current_time = datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc)

    def increment(_):
        rate_limits.consume(
            scope='concurrency',
            identity='user:1',
            maximum=100,
            window_seconds=60,
            current_time=current_time,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(increment, range(16)))

    with SessionLocal() as session:
        bucket = session.scalar(select(RateBucket))
        assert bucket.hits == 16
        assert bucket.expires_at == current_time + timedelta(seconds=60)


def test_lock_wait_past_expiry_starts_a_new_window(raw):
    clear_rate_buckets()
    key = rate_limits.bucket_key('lock-wait', 'user:1')
    with SessionLocal() as session:
        session.execute(
            text("""
                INSERT INTO auth_rate_limits (key, hits, expires_at)
                VALUES (:key, 1, clock_timestamp() + INTERVAL '200 milliseconds')
            """),
            {'key': key},
        )
        session.commit()

    with SessionLocal() as locker:
        locker.execute(
            text('SELECT key FROM auth_rate_limits WHERE key = :key FOR UPDATE'),
            {'key': key},
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                rate_limits.consume,
                scope='lock-wait',
                identity='user:1',
                maximum=1,
                window_seconds=60,
            )
            time.sleep(0.5)
            locker.commit()
            future.result(timeout=5)

    with SessionLocal() as session:
        bucket = session.get(RateBucket, key)
        assert bucket.hits == 1
        assert session.scalar(
            text('SELECT expires_at > clock_timestamp() FROM auth_rate_limits WHERE key = :key'),
            {'key': key},
        ) is True


def test_health_does_not_consume_or_depend_on_rate_limit(raw, monkeypatch):
    clear_rate_buckets()
    monkeypatch.setattr(rate_limits, 'UNAUTHENTICATED_LIMIT', 0)

    assert raw.get('/api/health').status_code == 200
    assert raw.get('/api/health', headers={'X-Forwarded-For': '203.0.113.1'}).status_code == 200
    assert raw.get('/metrics').status_code == 404
    assert raw.get('/api/auth/providers').status_code == 429


def test_expired_bucket_cleanup_is_bounded(raw):
    clear_rate_buckets()
    current_time = datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc)
    with SessionLocal() as session:
        session.add_all([
            RateBucket(key=f'expired-{index}', hits=1, expires_at=current_time - timedelta(seconds=index + 1))
            for index in range(3)
        ])
        session.add(RateBucket(key='active', hits=1, expires_at=current_time + timedelta(seconds=1)))
        session.commit()

    assert cleanup_rate_limits(batch_size=2, current_time=current_time) == 2
    assert cleanup_rate_limits(batch_size=2, current_time=current_time) == 1
    assert cleanup_rate_limits(batch_size=2, current_time=current_time) == 0
    with SessionLocal() as session:
        assert session.scalars(select(RateBucket.key)).all() == ['active']
