import {ErrorHandler, Provider} from '@angular/core';
import * as Sentry from '@sentry/angular';

import {appConfig} from './app.config';
import {initializeErrorTracking} from './error-tracking';


describe('error tracking', () => {
    it('registers an application error handler', () => {
        const providers = (appConfig.providers ?? []) as Provider[];
        const configured = providers.some(provider =>
            typeof provider === 'object' && provider !== null && 'provide' in provider && provider.provide === ErrorHandler
        );

        expect(configured).toBeTrue();
    });

    it('does not initialize or make a transport available without a DSN', () => {
        const initialized: unknown[] = [];

        expect((initializeErrorTracking as unknown as Function)({}, (options: unknown) => initialized.push(options))).toBeFalse();
        expect(initialized).toEqual([]);
    });

    it('configures Angular capture with all optional collection disabled', () => {
        let options: any;
        const initialized = (configured: unknown) => options = configured;

        expect((initializeErrorTracking as unknown as Function)({
            sentryDsn: 'https://public@example.invalid/1',
            environment: 'test',
            release: 'minutes@abc123'
        }, initialized)).toBeTrue();

        expect(options.dsn).toBe('https://public@example.invalid/1');
        expect(options.environment).toBe('test');
        expect(options.release).toBe('minutes@abc123');
        expect(options.sendDefaultPii).toBeFalse();
        expect(options.tracesSampleRate).toBe(0);
        expect(options.profilesSampleRate).toBe(0);
        expect(options.replaysSessionSampleRate).toBe(0);
        expect(options.replaysOnErrorSampleRate).toBe(0);
        expect(options.enableLogs).toBeFalse();
    });

    it('captures a thrown exception with a scrubbed stack through an in-memory transport', async () => {
        const events: any[] = [];
        const initialized = initializeErrorTracking({
            sentryDsn: 'https://public@example.invalid/1',
            environment: 'test',
            release: 'minutes@abc123'
        }, options => Sentry.init({
            ...options,
            transport: () => ({
                send: envelope => {
                    for (const [headers, payload] of envelope[1]) {
                        if (headers.type === 'event') {
                            events.push(payload);
                        }
                    }
                    return Promise.resolve({statusCode: 200});
                },
                flush: () => Promise.resolve(true)
            })
        }));

        expect(initialized).toBeTrue();
        try {
            try {
                throw new TypeError('PRIVATE_EXCEPTION_SENTINEL private@example.com note-123');
            } catch (error) {
                Sentry.createErrorHandler({logErrors: false}).handleError(error);
            }
            expect(await Sentry.flush(2000)).toBeTrue();
        } finally {
            await Sentry.close(2000);
        }

        expect(events.length).toBe(1);
        const exception = events[0].exception.values[0];
        expect(exception.type).toBe('TypeError');
        expect(exception.value).toBeUndefined();
        expect(exception.stacktrace.frames.length).toBeGreaterThan(0);
        const serialized = JSON.stringify(events[0]);
        expect(serialized).not.toContain('PRIVATE_EXCEPTION_SENTINEL');
        expect(serialized).not.toContain('private@example.com');
        expect(serialized).not.toContain('note-123');
    });

    it('retains only safe exception stack and correlation fields from the complete payload and breadcrumbs', () => {
        let options: any;
        const sentinel = 'PRIVATE_SENTINEL private@example.com 192.0.2.1 note-123';
        (initializeErrorTracking as unknown as Function)({
            sentryDsn: 'https://public@example.invalid/1',
            environment: 'test',
            release: 'minutes@abc123'
        }, (configured: unknown) => options = configured);

        const event = options.beforeSend({
            event_id: 'a'.repeat(32),
            timestamp: 1,
            platform: 'javascript',
            level: 'error',
            environment: 'test',
            release: 'minutes@abc123',
            message: sentinel,
            request: {
                url: `https://app.example/api/notes/note-123?token=${sentinel}#fragment`,
                headers: {authorization: sentinel, cookie: sentinel},
                cookies: {refresh_token: sentinel},
                data: {content: sentinel},
                query_string: sentinel,
                env: {REMOTE_ADDR: '192.0.2.1'}
            },
            user: {email: 'private@example.com', ip_address: '192.0.2.1'},
            contexts: {trace: {trace_id: sentinel}},
            extra: {note_content: sentinel},
            tags: {request_id: 'request-safe-123', unsafe: sentinel},
            exception: {values: [{
                type: 'TypeError',
                value: sentinel,
                stacktrace: {frames: [{
                    filename: `https://app.example/main-ABC123.js?secret=${sentinel}#fragment`,
                    function: 'saveNote',
                    lineno: 42,
                    colno: 7,
                    vars: {secret: sentinel},
                    context_line: sentinel
                }]}
            }]},
            breadcrumbs: [{
                category: 'http',
                type: 'http',
                level: 'info',
                message: sentinel,
                data: {url: sentinel, Authorization: sentinel}
            }]
        }, {});

        const serialized = JSON.stringify(event);
        expect(serialized).not.toContain('PRIVATE_SENTINEL');
        expect(serialized).not.toContain('private@example.com');
        expect(serialized).not.toContain('192.0.2.1');
        expect(serialized).not.toContain('note-123');
        expect(event).toEqual({
            event_id: 'a'.repeat(32),
            timestamp: 1,
            platform: 'javascript',
            level: 'error',
            environment: 'test',
            release: 'minutes@abc123',
            exception: {values: [{
                type: 'TypeError',
                stacktrace: {frames: [{filename: 'main-ABC123.js', function: 'saveNote', lineno: 42}]}
            }]},
            breadcrumbs: [{category: 'http', type: 'http', level: 'info'}],
            tags: {request_id: 'request-safe-123'}
        });
        expect(options.beforeBreadcrumb({
            category: 'http', type: 'http', level: 'info', message: sentinel, data: {url: sentinel}
        }, {})).toEqual({category: 'http', type: 'http', level: 'info'});

        const poisonedMetadata = options.beforeSend({
            event_id: sentinel,
            timestamp: 2,
            platform: sentinel,
            level: sentinel,
            environment: 'test',
            release: 'minutes@abc123'
        }, {});
        expect(JSON.stringify(poisonedMetadata)).not.toContain('PRIVATE_SENTINEL');
        expect(poisonedMetadata).toEqual({
            timestamp: 2,
            environment: 'test',
            release: 'minutes@abc123'
        });
    });

    it('rejects malformed runtime configuration instead of initializing', () => {
        const initialized: unknown[] = [];
        expect((initializeErrorTracking as unknown as Function)({
            sentryDsn: 'javascript:PRIVATE_SENTINEL',
            environment: 'unsafe value with spaces',
            release: 'unsafe"release'
        }, (options: unknown) => initialized.push(options))).toBeFalse();
        expect(initialized).toEqual([]);
    });
});
