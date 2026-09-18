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

        expect(auth.call).toHaveBeenCalledWith('DELETE', 'me', {
            password: '',
            confirmation: 'delete account'
        });
        expect(auth.clear).toHaveBeenCalled();
        expect(navigate).toHaveBeenCalledOnceWith('/login');
    });

    it('disables preference saving until the initial values load', async () => {
        let resolvePreferences!: (value: unknown) => void;
        auth.call.and.returnValue(new Promise(resolve => resolvePreferences = resolve));
        const loadingFixture = TestBed.createComponent(Account);
        loadingFixture.detectChanges();
        const saveButton = Array.from(
            loadingFixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
        ).find(button => button.textContent?.includes('Save notification preferences'))!;

        expect(saveButton.disabled).toBeTrue();
        resolvePreferences({
            reminders_enabled: false,
            digest_enabled: false,
            reminder_lead_minutes: 10
        });
        await loadingFixture.whenStable();
        loadingFixture.detectChanges();
        expect(saveButton.disabled).toBeFalse();
    });

    it('keeps preference saving disabled when the initial load fails', async () => {
        auth.call.and.rejectWith(new Error('network unavailable'));
        const failedFixture = TestBed.createComponent(Account);
        failedFixture.detectChanges();
        await failedFixture.whenStable();
        failedFixture.detectChanges();
        const saveButton = Array.from(
            failedFixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>
        ).find(button => button.textContent?.includes('Save notification preferences'))!;

        expect(saveButton.disabled).toBeTrue();
    });

    it('loads and saves opt-in notification preferences', async () => {
        auth.call.and.resolveTo({
            reminders_enabled: false,
            digest_enabled: true,
            reminder_lead_minutes: 30
        });

        await component.loadNotificationPreferences();

        expect(auth.call).toHaveBeenCalledWith('GET', 'notification-preferences');
        expect(component.remindersEnabled).toBeFalse();
        expect(component.digestEnabled).toBeTrue();
        expect(component.reminderLeadMinutes).toBe(30);

        component.remindersEnabled = true;
        component.reminderLeadMinutes = 45;
        auth.call.calls.reset();
        auth.call.and.resolveTo({
            reminders_enabled: true,
            digest_enabled: true,
            reminder_lead_minutes: 45
        });
        await component.saveNotificationPreferences();

        expect(auth.call).toHaveBeenCalledOnceWith('PUT', 'notification-preferences', {
            reminders_enabled: true,
            digest_enabled: true,
            reminder_lead_minutes: 45
        });
        expect(component.message).toBe('Notification preferences saved.');
    });
});
