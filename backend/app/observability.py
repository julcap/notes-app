import json
import logging
import re
import sys
import time
import traceback
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI


request_id: ContextVar[str | None] = ContextVar('request_id', default=None)
REQUEST_ID = re.compile(r'^[A-Za-z0-9._:-]{1,64}$')
SAFE_NAME = re.compile(r'^[A-Za-z0-9_.:-]{1,64}$')
SAFE_ROUTE = re.compile(r'^/[A-Za-z0-9_./{}:-]{0,127}$')
SAFE_METHOD = re.compile(r'^[A-Z]{1,32}$')
SAFE_CODE_NAME = re.compile(r'^[A-Za-z0-9_.<>:-]{1,128}$')
STRUCTURED_FIELDS = ('auth_event', 'outcome', 'auth_method', 'error_type')


class JsonFormatter(logging.Formatter):
    def format(self, record):
        event = getattr(record, 'event', None)
        trusted = record.name.startswith('app.') and isinstance(event, str) and bool(SAFE_NAME.fullmatch(event))
        if not trusted:
            event = 'dependency_log'
        payload = {
            'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            'level': record.levelname.lower(),
            'logger': record.name if SAFE_NAME.fullmatch(record.name) else 'unknown',
            'event': event,
            'request_id': request_id.get(),
        }
        if not trusted:
            return json.dumps(payload, separators=(',', ':'), ensure_ascii=True)
        for field in STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if isinstance(value, str) and SAFE_NAME.fullmatch(value):
                payload[field] = value
        method = getattr(record, 'method', None)
        if isinstance(method, str) and SAFE_METHOD.fullmatch(method):
            payload['method'] = method
        route = getattr(record, 'route', None)
        if isinstance(route, str) and SAFE_ROUTE.fullmatch(route):
            payload['route'] = route
        status = getattr(record, 'status', None)
        if isinstance(status, int) and 100 <= status <= 599:
            payload['status'] = status
        duration_ms = getattr(record, 'duration_ms', None)
        if isinstance(duration_ms, (int, float)) and duration_ms >= 0:
            payload['duration_ms'] = round(duration_ms, 3)
        stack = getattr(record, 'stack', None)
        if isinstance(stack, list):
            safe_frames = []
            for frame in stack:
                if not isinstance(frame, dict) or set(frame) != {'file', 'line', 'function'}:
                    continue
                filename, line, function = frame['file'], frame['line'], frame['function']
                if (
                    isinstance(filename, str)
                    and SAFE_CODE_NAME.fullmatch(filename)
                    and isinstance(line, int)
                    and line > 0
                    and isinstance(function, str)
                    and SAFE_CODE_NAME.fullmatch(function)
                ):
                    safe_frames.append(frame)
            if safe_frames:
                payload['stack'] = safe_frames
        return json.dumps(payload, separators=(',', ':'), ensure_ascii=True)


def configure_logging(stream=None):
    logging.captureWarnings(True)
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    for logger in logging.root.manager.loggerDict.values():
        if not isinstance(logger, logging.Logger):
            continue
        logger.handlers.clear()
        logger.disabled = logger.name == 'uvicorn.access'
        logger.propagate = True
    for name in ('botocore', 'boto3', 'sqlalchemy.engine'):
        logging.getLogger(name).setLevel(logging.WARNING)


def log_event(logger, level, event, **fields):
    logger.log(level, event, extra={'event': event, **fields})


def log_auth_event(auth_event, outcome, auth_method=None):
    fields = {'auth_event': auth_event, 'outcome': outcome}
    if auth_method:
        fields['auth_method'] = auth_method
    log_event(logging.getLogger('app.auth.audit'), logging.INFO, 'auth_event', **fields)


def safe_stack(error):
    return [
        {
            'file': Path(frame.filename).name,
            'line': frame.lineno,
            'function': frame.name,
        }
        for frame in traceback.extract_tb(error.__traceback__)
    ]


def accepted_request_id(scope):
    for key, value in scope.get('headers', ()):
        if key.lower() != b'x-request-id':
            continue
        try:
            candidate = value.decode('ascii')
        except UnicodeDecodeError:
            break
        if REQUEST_ID.fullmatch(candidate):
            return candidate
        break
    return uuid.uuid4().hex


def route_template(scope):
    route = scope.get('route')
    path = getattr(route, 'path', None)
    return path if isinstance(path, str) and SAFE_ROUTE.fullmatch(path) else '/unmatched'


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger('app.request')

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        current_request_id = accepted_request_id(scope)
        token = request_id.set(current_request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_request_id(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                headers = list(message.get('headers', ()))
                headers = [(key, value) for key, value in headers if key.lower() != b'x-request-id']
                headers.append((b'x-request-id', current_request_id.encode('ascii')))
                message = {**message, 'headers': headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as error:
            status = 500
            log_event(
                self.logger,
                logging.ERROR,
                'unhandled_error',
                error_type=type(error).__name__,
                stack=safe_stack(error),
            )
            raise
        finally:
            level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
            log_event(
                self.logger,
                level,
                'request_completed',
                method=scope['method'],
                route=route_template(scope),
                status=status,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
            request_id.reset(token)


class ObservedFastAPI(FastAPI):
    def build_middleware_stack(self):
        return RequestLoggingMiddleware(super().build_middleware_stack())
