import math
import os
import re

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from .observability import REQUEST_ID, request_id


SAFE_TOKEN = re.compile(r'^[A-Za-z0-9._:@/+\-=]{1,128}$')
SAFE_CODE_NAME = re.compile(r'^[A-Za-z0-9_.<>:@+\-]{1,160}$')
SAFE_BREADCRUMB = re.compile(r'^[A-Za-z0-9_.:\-]{1,64}$')
SAFE_EVENT_ID = re.compile(r'^[a-fA-F0-9]{32}$')
SAFE_TIMESTAMP = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z$')


def safe_token(value):
    return value if isinstance(value, str) and SAFE_TOKEN.fullmatch(value) else None


def safe_code_name(value, fallback=None):
    if not isinstance(value, str):
        return fallback
    candidate = re.split(r'[/\\]', value.split('?', 1)[0].split('#', 1)[0])[-1]
    return candidate if SAFE_CODE_NAME.fullmatch(candidate) else fallback


def scrub_breadcrumb(breadcrumb, hint=None):
    safe = {}
    for field in ('category', 'type', 'level'):
        value = breadcrumb.get(field)
        if isinstance(value, str) and SAFE_BREADCRUMB.fullmatch(value):
            safe[field] = value
    timestamp = breadcrumb.get('timestamp')
    if isinstance(timestamp, (int, float)) and timestamp >= 0:
        safe['timestamp'] = timestamp
    return safe or None


def scrub_stacktrace(stacktrace):
    frames = []
    for frame in stacktrace.get('frames', ()) if isinstance(stacktrace, dict) else ():
        if not isinstance(frame, dict):
            continue
        filename = safe_code_name(frame.get('filename'))
        function = safe_code_name(frame.get('function'))
        lineno = frame.get('lineno')
        if filename is None or function is None or not isinstance(lineno, int) or lineno <= 0:
            continue
        frames.append({'filename': filename, 'function': function, 'lineno': lineno})
    return {'frames': frames} if frames else None


def scrub_exception(exception):
    values = []
    raw_values = exception.get('values', ()) if isinstance(exception, dict) else ()
    for value in raw_values:
        if not isinstance(value, dict):
            continue
        exception_type = safe_code_name(value.get('type'))
        stacktrace = scrub_stacktrace(value.get('stacktrace'))
        if exception_type is None:
            continue
        safe = {'type': exception_type}
        if stacktrace is not None:
            safe['stacktrace'] = stacktrace
        values.append(safe)
    return {'values': values} if values else None


def scrub_event(event, hint=None):
    safe = {}
    event_id = event.get('event_id')
    if isinstance(event_id, str) and SAFE_EVENT_ID.fullmatch(event_id):
        safe['event_id'] = event_id
    timestamp = event.get('timestamp')
    if (
        isinstance(timestamp, (int, float))
        and not isinstance(timestamp, bool)
        and math.isfinite(timestamp)
        and timestamp >= 0
    ) or (isinstance(timestamp, str) and SAFE_TIMESTAMP.fullmatch(timestamp)):
        safe['timestamp'] = timestamp
    for field in ('platform', 'level'):
        value = safe_token(event.get(field))
        if value is not None:
            safe[field] = value
    for field in ('environment', 'release'):
        value = safe_token(event.get(field))
        if value is not None:
            safe[field] = value
    exception = scrub_exception(event.get('exception'))
    if exception is not None:
        safe['exception'] = exception
    raw_breadcrumbs = event.get('breadcrumbs')
    values = raw_breadcrumbs.get('values', ()) if isinstance(raw_breadcrumbs, dict) else ()
    breadcrumbs = [scrubbed for item in values if (scrubbed := scrub_breadcrumb(item)) is not None]
    if breadcrumbs:
        safe['breadcrumbs'] = {'values': breadcrumbs}
    current_request_id = request_id.get()
    if isinstance(current_request_id, str) and REQUEST_ID.fullmatch(current_request_id):
        safe['tags'] = {'request_id': current_request_id}
    return safe


def initialize_error_tracking(init=sentry_sdk.init, transport=None):
    dsn = os.environ.get('SENTRY_DSN', '').strip()
    if not dsn:
        return False
    options = {
        'dsn': dsn,
        'environment': safe_token(os.environ.get('SENTRY_ENVIRONMENT', '').strip()),
        'release': safe_token(os.environ.get('SENTRY_RELEASE', '').strip()),
        'send_default_pii': False,
        'traces_sample_rate': 0.0,
        'profiles_sample_rate': 0.0,
        'enable_logs': False,
        'before_send': scrub_event,
        'before_breadcrumb': scrub_breadcrumb,
        'integrations': [
            FastApiIntegration(transaction_style='endpoint', middleware_spans=False),
            LoggingIntegration(level=None, event_level=None, capture_sentry_logs=False),
        ],
    }
    if transport is not None:
        options['transport'] = transport
    init(**options)
    return True
