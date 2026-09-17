import {ComponentFixture, TestBed} from '@angular/core/testing';
import {provideRouter, Router} from '@angular/router';

import {AuthService} from '../auth/auth.service';
import {User} from '../auth/user.model';
import {Account} from './account';

const user: User = {
    id: 1,
    email: 'reader@example.com',
    pending_email: null,
    display_name: 'Reader',
    email_verified: true,
    auth_provider: 'google',
    has_password: false,
    totp_enabled: false,
    created_at: '2026-09-17T00:00:00Z'
};

describe('Account', () => {
    let fixture: ComponentFixture<Account>;
    let component: Account;
    let auth: jasmine.SpyObj<AuthService>;

    beforeEach(async () => {
        auth = jasmine.createSpyObj<AuthService>(
            'AuthService',
            ['call', 'action', 'updateProfile', 'clear', 'logout'],
            {user}
        );
        await TestBed.configureTestingModule({
            imports: [Account],
            providers: [{provide: AuthService, useValue: auth}, provideRouter([])]
        }).compileComponents();
        fixture = TestBed.createComponent(Account);
        component = fixture.componentInstance;
        fixture.detectChanges();
        await fixture.whenStable();
    });

    it('rejects a password change when confirmation does not match', async () => {
        component.currentPassword = 'old-password';
        component.newPassword = 'long-password-1';
        component.newPasswordConfirmation = 'long-password-2';

        await component.changePassword();

        expect(auth.action).not.toHaveBeenCalled();
        expect(component.error).toContain('matching confirmation');
    });

    it('requires and forwards the account deletion confirmation', async () => {
        component.confirmDelete = true;
        fixture.detectChanges();
        await fixture.whenStable();
        fixture.detectChanges();
        const deleteButton = fixture.nativeElement.querySelector('.danger-fill') as HTMLButtonElement;
        expect(deleteButton.disabled).toBeTrue();

        component.deleteConfirmation = 'delete account';
        fixture.detectChanges();
        expect(deleteButton.disabled).toBeFalse();

        auth.call.and.resolveTo({});
        const navigate = spyOn(TestBed.inject(Router), 'navigateByUrl').and.resolveTo(true);
        await component.deleteAccount();

        expect(auth.call).toHaveBeenCalledOnceWith('DELETE', 'me', {
            password: '',
            confirmation: 'delete account'
        });
        expect(auth.clear).toHaveBeenCalled();
        expect(navigate).toHaveBeenCalledOnceWith('/login');
    });
});
