import {ErrorHandler, Provider} from '@angular/core';
import * as Sentry from '@sentry/angular';
import type {Breadcrumb, BreadcrumbHint, BrowserOptions, ErrorEvent, Event, EventHint, StackFrame} from '@sentry/angular';


export interface RuntimeConfig {
    sentryDsn?: string;
    environment?: string;
    release?: string;
}

declare global {
    interface Window {
        __MINUTES_CONFIG__?: RuntimeConfig;
    }
}

const SAFE_DSN = /^https:\/\/[A-Za-z0-9._~-]+@[A-Za-z0-9.-]+(?::[0-9]+)?\/[A-Za-z0-9._~/-]+$/;
const SAFE_TOKEN = /^[A-Za-z0-9._:@/+\-=]{1,128}$/;
const SAFE_CODE_NAME = /^[A-Za-z0-9_.<>:@+\-]{1,160}$/;
const SAFE_BREADCRUMB = /^[A-Za-z0-9_.:\-]{1,64}$/;
const SAFE_EVENT_ID = /^[a-fA-F0-9]{32}$/;

export const runtimeConfig = window.__MINUTES_CONFIG__ ?? {};

function safeToken(value: unknown): string | undefined {
    return typeof value === 'string' && SAFE_TOKEN.test(value) ? value : undefined;
}

function safeCodeName(value: unknown): string | undefined {
    if (typeof value !== 'string') {
        return undefined;
    }
    const withoutLocation = value.split('?', 1)[0].split('#', 1)[0];
    const candidate = withoutLocation.split(/[\\/]/).at(-1);
    return candidate && SAFE_CODE_NAME.test(candidate) ? candidate : undefined;
}

function scrubFrame(frame: StackFrame): StackFrame | undefined {
    const filename = safeCodeName(frame.filename);
    const functionName = safeCodeName(frame.function);
    if (!filename || !functionName || typeof frame.lineno !== 'number' || frame.lineno <= 0) {
        return undefined;
    }
    return {filename, function: functionName, lineno: frame.lineno};
}

export function scrubBreadcrumb(breadcrumb: Breadcrumb, _hint?: BreadcrumbHint): Breadcrumb | null {
    const safe: Breadcrumb = {};
    if (typeof breadcrumb.category === 'string' && SAFE_BREADCRUMB.test(breadcrumb.category)) {
        safe.category = breadcrumb.category;
    }
    if (typeof breadcrumb.type === 'string' && SAFE_BREADCRUMB.test(breadcrumb.type)) {
        safe.type = breadcrumb.type;
    }
    if (typeof breadcrumb.level === 'string' && SAFE_BREADCRUMB.test(breadcrumb.level)) {
        safe.level = breadcrumb.level;
    }
    if (typeof breadcrumb.timestamp === 'number' && breadcrumb.timestamp >= 0) {
        safe.timestamp = breadcrumb.timestamp;
    }
    return Object.keys(safe).length ? safe : null;
}

export function scrubEvent(event: ErrorEvent, _hint?: EventHint): ErrorEvent {
    const safe: Event = {};
    if (typeof event.event_id === 'string' && SAFE_EVENT_ID.test(event.event_id)) {
        safe.event_id = event.event_id;
    }
    if (typeof event.timestamp === 'number' && Number.isFinite(event.timestamp) && event.timestamp >= 0) {
        safe.timestamp = event.timestamp;
    }
    if (typeof event.platform === 'string' && SAFE_TOKEN.test(event.platform)) {
        safe.platform = event.platform;
    }
    if (typeof event.level === 'string' && SAFE_TOKEN.test(event.level)) {
        safe.level = event.level;
    }
    const environment = safeToken(event.environment);
    const release = safeToken(event.release);
    if (environment) {
        safe.environment = environment;
    }
    if (release) {
        safe.release = release;
    }
    const exceptionValues = (event.exception?.values ?? []).flatMap(value => {
        const exceptionType = safeCodeName(value.type);
        if (!exceptionType) {
            return [];
        }
        const frames = (value.stacktrace?.frames ?? []).flatMap(frame => {
            const scrubbed = scrubFrame(frame);
            return scrubbed ? [scrubbed] : [];
        });
        return [{
            type: exceptionType,
            ...(frames.length ? {stacktrace: {frames}} : {})
        }];
    });
    if (exceptionValues.length) {
        safe.exception = {values: exceptionValues};
    }
    const breadcrumbs = (event.breadcrumbs ?? []).flatMap(breadcrumb => {
        const scrubbed = scrubBreadcrumb(breadcrumb);
        return scrubbed ? [scrubbed] : [];
    });
    if (breadcrumbs.length) {
        safe.breadcrumbs = breadcrumbs;
    }
    const requestId = safeToken(event.tags?.['request_id']);
    if (requestId) {
        safe.tags = {request_id: requestId};
    }
    return safe as ErrorEvent;
}

export function initializeErrorTracking(
    config: RuntimeConfig = runtimeConfig,
    init: (options: BrowserOptions) => unknown = Sentry.init
): boolean {
    const dsn = config.sentryDsn?.trim();
    if (!dsn || !SAFE_DSN.test(dsn)) {
        return false;
    }
    init({
        dsn,
        environment: safeToken(config.environment?.trim()),
        release: safeToken(config.release?.trim()),
        sendDefaultPii: false,
        tracesSampleRate: 0,
        profilesSampleRate: 0,
        replaysSessionSampleRate: 0,
        replaysOnErrorSampleRate: 0,
        enableLogs: false,
        beforeSend: scrubEvent,
        beforeBreadcrumb: scrubBreadcrumb
    });
    return true;
}

const errorTrackingEnabled = initializeErrorTracking();

export const errorTrackingProvider: Provider = {
    provide: ErrorHandler,
    useFactory: () => errorTrackingEnabled ? Sentry.createErrorHandler({logErrors: false}) : new ErrorHandler()
};
