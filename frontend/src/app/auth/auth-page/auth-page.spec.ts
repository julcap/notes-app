import {provideHttpClient} from '@angular/common/http';
import {provideHttpClientTesting} from '@angular/common/http/testing';
import {ComponentFixture, TestBed} from '@angular/core/testing';
import {ActivatedRoute, convertToParamMap, provideRouter, Router} from '@angular/router';

import {AuthService} from '../auth.service';
import {AuthPage} from './auth-page';

describe('AuthPage', () => {
    let fixture: ComponentFixture<AuthPage>;
    let component: AuthPage;
    let auth: jasmine.SpyObj<AuthService>;

    beforeEach(async () => {
        auth = jasmine.createSpyObj<AuthService>('AuthService', ['action', 'refresh', 'ensure', 'clear']);
        await TestBed.configureTestingModule({
            imports: [AuthPage],
            providers: [
                provideRouter([]),
                provideHttpClient(),
                provideHttpClientTesting(),
                {provide: AuthService, useValue: auth},
                {
                    provide: ActivatedRoute,
                    useValue: {snapshot: {data: {mode: 'register'}, queryParamMap: convertToParamMap({})}}
                }
            ]
        }).compileComponents();
        fixture = TestBed.createComponent(AuthPage);
        component = fixture.componentInstance;
        fixture.detectChanges();
        await fixture.whenStable();
    });

    function submitButton(): HTMLButtonElement {
        return fixture.nativeElement.querySelector('form button[type="submit"]');
    }

    it('keeps the registration form disabled until email and matching policy-compliant passwords are present', async () => {
        expect(submitButton().disabled).toBeTrue();

        component.email = 'reader@example.com';
        component.password = 'long-password-1';
        component.confirmation = 'different-password-2';
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();
        expect(submitButton().disabled).toBeTrue();

        component.confirmation = component.password;
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();
        expect(submitButton().disabled).toBeFalse();
    });

    it('links registration to the public privacy policy and terms', () => {
        const links = Array.from(fixture.nativeElement.querySelectorAll('a')) as HTMLAnchorElement[];

        expect(links.some(link => link.getAttribute('href') === '/privacy')).toBeTrue();
        expect(links.some(link => link.getAttribute('href') === '/terms')).toBeTrue();
    });

    it('keeps the login form disabled until both credentials are present', async () => {
        component.mode = 'login';
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();
        expect(submitButton().disabled).toBeTrue();

        component.email = 'reader@example.com';
        component.password = 'login-password';
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();
        expect(submitButton().disabled).toBeFalse();
    });

    it('rejects registration when password confirmation does not match', async () => {
        component.email = 'reader@example.com';
        component.password = 'long-password-1';
        component.confirmation = 'long-password-2';

        await component.submit();

        expect(auth.action).not.toHaveBeenCalled();
        expect(component.error).toContain('matching confirmation');
        expect(component.busy).toBeFalse();
    });

    it('submits valid registration details and navigates to the workspace', async () => {
        const navigate = spyOn(TestBed.inject(Router), 'navigateByUrl').and.resolveTo(true);
        auth.action.and.resolveTo({});
        component.email = 'reader@example.com';
        component.password = 'long-password-1';
        component.confirmation = component.password;
        component.displayName = 'Reader';
        component.remember = true;

        await component.submit();

        expect(auth.action).toHaveBeenCalledOnceWith('register', {
            email: 'reader@example.com',
            password: 'long-password-1',
            password_confirmation: 'long-password-1',
            display_name: 'Reader',
            remember: true
        });
        expect(navigate).toHaveBeenCalledOnceWith('/');
    });
});
