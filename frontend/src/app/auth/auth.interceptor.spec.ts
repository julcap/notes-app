import {HttpClient, provideHttpClient, withInterceptors} from '@angular/common/http';
import {HttpTestingController, provideHttpClientTesting, TestRequest} from '@angular/common/http/testing';
import {TestBed} from '@angular/core/testing';
import {provideRouter, Router} from '@angular/router';
import {firstValueFrom} from 'rxjs';

import {authInterceptor} from './auth.interceptor';
import {AuthService} from './auth.service';
import {User} from './user.model';

const user: User = {
    id: 1,
    email: 'reader@example.com',
    pending_email: null,
    display_name: 'Reader',
    email_verified: true,
    auth_provider: 'local',
    has_password: true,
    totp_enabled: false,
    created_at: '2026-09-17T00:00:00Z'
};

describe('authInterceptor', () => {
    let client: HttpClient;
    let http: HttpTestingController;
    let auth: AuthService;
    let router: Router;

    beforeEach(() => {
        TestBed.configureTestingModule({
            providers: [
                provideHttpClient(withInterceptors([authInterceptor])),
                provideHttpClientTesting(),
                provideRouter([])
            ]
        });
        client = TestBed.inject(HttpClient);
        http = TestBed.inject(HttpTestingController);
        auth = TestBed.inject(AuthService);
        router = TestBed.inject(Router);
        auth.token = 'old-token';
    });

    afterEach(() => http.verify());

    function rejectAsUnauthorized(request: TestRequest) {
        request.flush({detail: 'expired'}, {status: 401, statusText: 'Unauthorized'});
    }

    it('retries a notes request once with the refreshed access token', async () => {
        const pending = firstValueFrom(client.get('/api/notes'));
        const first = http.expectOne('/api/notes');
        expect(first.request.headers.get('Authorization')).toBe('Bearer old-token');
        rejectAsUnauthorized(first);

        http.expectOne('/api/auth/refresh').flush({access_token: 'new-token', user});
        await new Promise(resolve => setTimeout(resolve, 0));
        const retry = http.expectOne('/api/notes');
        expect(retry.request.headers.get('Authorization')).toBe('Bearer new-token');
        rejectAsUnauthorized(retry);

        await expectAsync(pending).toBeRejectedWith(jasmine.objectContaining({status: 401}));
        http.expectNone('/api/auth/refresh');
    });

    it('deduplicates refresh while concurrent notes requests retry', async () => {
        const firstPending = firstValueFrom(client.get('/api/notes/one'));
        const secondPending = firstValueFrom(client.get('/api/notes/two'));
        rejectAsUnauthorized(http.expectOne('/api/notes/one'));
        rejectAsUnauthorized(http.expectOne('/api/notes/two'));

        const refreshes = http.match('/api/auth/refresh');
        expect(refreshes.length).toBe(1);
        refreshes[0].flush({access_token: 'new-token', user});
        await new Promise(resolve => setTimeout(resolve, 0));

        const firstRetry = http.expectOne('/api/notes/one');
        const secondRetry = http.expectOne('/api/notes/two');
        expect(firstRetry.request.headers.get('Authorization')).toBe('Bearer new-token');
        expect(secondRetry.request.headers.get('Authorization')).toBe('Bearer new-token');
        firstRetry.flush({id: 'one'});
        secondRetry.flush({id: 'two'});

        await expectAsync(Promise.all([firstPending, secondPending])).toBeResolvedTo([{id: 'one'}, {id: 'two'}]);
    });

    it('redirects to login when refresh fails', async () => {
        const navigate = spyOn(router, 'navigateByUrl').and.resolveTo(true);
        const pending = firstValueFrom(client.get('/api/notes'));
        rejectAsUnauthorized(http.expectOne('/api/notes'));
        http.expectOne('/api/auth/refresh').flush({}, {status: 401, statusText: 'Unauthorized'});

        await expectAsync(pending).toBeRejected();
        expect(navigate).toHaveBeenCalledWith('/login');
    });
});
