import {ApplicationConfig} from '@angular/core';
import {provideHttpClient, withInterceptors} from '@angular/common/http';
import {provideRouter} from '@angular/router';

import {authInterceptor} from './auth/auth.interceptor';
import {routes} from './app.routes';
import {errorTrackingProvider} from './error-tracking';

export const appConfig: ApplicationConfig = {
    providers: [
        errorTrackingProvider,
        provideHttpClient(withInterceptors([authInterceptor])),
        provideRouter(routes),
    ],
};
