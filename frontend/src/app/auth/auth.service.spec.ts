import {provideHttpClient} from '@angular/common/http';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {TestBed} from '@angular/core/testing';
import {provideRouter} from '@angular/router';

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

describe('AuthService', () => {
    let service: AuthService;
    let http: HttpTestingController;

    beforeEach(() => {
        TestBed.configureTestingModule({
            providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])]
        });
        service = TestBed.inject(AuthService);
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('accepts the session returned by an auth request', async () => {
        const pending = service.action('login', {email: user.email, password: 'correct horse'});
        const request = http.expectOne('/api/auth/login');

        expect(request.request.method).toBe('POST');
        expect(request.request.body).toEqual({email: user.email, password: 'correct horse'});
        request.flush({access_token: 'access-token', user});

        await expectAsync(pending).toBeResolved();
        expect(service.token).toBe('access-token');
        expect(service.user).toEqual(user);
    });

    it('deduplicates concurrent refresh requests', async () => {
        const first = service.refresh();
        const second = service.refresh();

        expect(second).toBe(first);
        const request = http.expectOne('/api/auth/refresh');
        expect(request.request.method).toBe('POST');
        request.flush({access_token: 'refreshed-token', user});

        await expectAsync(Promise.all([first, second])).toBeResolvedTo([true, true]);
        expect(service.token).toBe('refreshed-token');
    });

    it('clears the local session when refresh fails', async () => {
        service.accept({access_token: 'expired-token', user});
        const pending = service.refresh();
        http.expectOne('/api/auth/refresh').flush({}, {status: 401, statusText: 'Unauthorized'});

        await expectAsync(pending).toBeResolvedTo(false);
        expect(service.token).toBe('');
        expect(service.user).toBeNull();
    });
});
