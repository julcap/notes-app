import {TestBed} from '@angular/core/testing';
import {ActivatedRouteSnapshot, provideRouter, Router, RouterStateSnapshot, UrlTree} from '@angular/router';

import {authGuard} from './auth.guard';
import {AuthService} from './auth.service';

function runGuard() {
    return TestBed.runInInjectionContext(() => authGuard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot));
}

describe('authGuard', () => {
    let auth: jasmine.SpyObj<AuthService>;

    beforeEach(() => {
        auth = jasmine.createSpyObj<AuthService>('AuthService', ['ensure']);
        TestBed.configureTestingModule({
            providers: [
                {provide: AuthService, useValue: auth},
                provideRouter([])
            ]
        });
    });

    it('allows an authenticated user', async () => {
        auth.ensure.and.resolveTo(true);
        await expectAsync(Promise.resolve(runGuard())).toBeResolvedTo(true);
    });

    it('returns the login URL tree for an unauthenticated user', async () => {
        auth.ensure.and.resolveTo(false);
        const result = await Promise.resolve(runGuard());

        expect(result instanceof UrlTree).toBeTrue();
        expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/login');
    });
});
