import {Component, OnInit, inject} from '@angular/core';
import {CommonModule} from '@angular/common';
import {FormsModule} from '@angular/forms';
import {DomSanitizer, SafeHtml} from '@angular/platform-browser';
import {Router, RouterLink} from '@angular/router';

import {AuthService} from '../auth/auth.service';
import {errorText} from '../auth/error-text';
import {validPassword} from '../auth/password-policy';
import {NavRail} from '../shell/nav-rail';

@Component({
    selector: 'account-page',
    standalone: true,
    imports: [CommonModule, FormsModule, RouterLink, NavRail],
    templateUrl: './account.html'
})
export class Account implements OnInit {
    auth = inject(AuthService);
    private router = inject(Router);
    private sanitizer = inject(DomSanitizer);

    busy = false;
    error = '';
    message = '';

    displayName = '';
    email = '';

    remindersEnabled = false;
    digestEnabled = false;
    reminderLeadMinutes = 10;
    notificationPreferencesLoading = true;
    private notificationPreferencesReady: Promise<void> = Promise.resolve();

    currentPassword = '';
    newPassword = '';
    newPasswordConfirmation = '';

    mfaSecret = '';
    mfaQr: SafeHtml | null = null;
    mfaCode = '';
    backupCodes: string[] | null = null;
    disablePassword = '';
    disableCode = '';

    confirmDelete = false;
    deletePassword = '';
    deleteConfirmation = '';

    get validNewPassword() {
        return validPassword(this.newPassword);
    }

    ngOnInit() {
        this.sync();
        this.notificationPreferencesReady = this.loadNotificationPreferences();
    }

    private sync() {
        this.displayName = this.auth.user?.display_name || '';
        this.email = this.auth.user?.email || '';
    }

    private async run(fn: () => Promise<string | void>) {
        if (this.busy) return;
        this.busy = true;
        this.error = '';
        this.message = '';
        try {
            this.message = (await fn()) || '';
        } catch (e) {
            this.error = errorText(e);
        } finally {
            this.busy = false;
        }
    }

    saveProfile() {
        return this.run(async () => {
            const changes: Record<string, string> = {};
            if (this.displayName !== (this.auth.user?.display_name || '')) changes['display_name'] = this.displayName;
            if (this.email !== (this.auth.user?.email || '')) changes['email'] = this.email;
            if (!Object.keys(changes).length) return;
            const result = await this.auth.call('PUT', 'me', changes);
            await this.auth.updateProfile();
            this.sync();
            return result.message || 'Saved.';
        });
    }

    async loadNotificationPreferences() {
        this.notificationPreferencesLoading = true;
        try {
            const preferences = await this.auth.call('GET', 'notification-preferences');
            if (!preferences) return;
            this.remindersEnabled = preferences.reminders_enabled;
            this.digestEnabled = preferences.digest_enabled;
            this.reminderLeadMinutes = preferences.reminder_lead_minutes;
            this.notificationPreferencesLoading = false;
        } catch (e) {
            this.error = errorText(e);
        }
    }

    saveNotificationPreferences() {
        return this.run(async () => {
            await this.notificationPreferencesReady;
            const preferences = await this.auth.call('PUT', 'notification-preferences', {
                reminders_enabled: this.remindersEnabled,
                digest_enabled: this.digestEnabled,
                reminder_lead_minutes: this.reminderLeadMinutes
            });
            this.remindersEnabled = preferences.reminders_enabled;
            this.digestEnabled = preferences.digest_enabled;
            this.reminderLeadMinutes = preferences.reminder_lead_minutes;
            return 'Notification preferences saved.';
        });
    }

    changePassword() {
        return this.run(async () => {
            if (!this.validNewPassword || this.newPassword !== this.newPasswordConfirmation) throw new Error('Use a password meeting the policy and matching confirmation.');
            await this.auth.action('change-password', {
                current_password: this.currentPassword,
                password: this.newPassword,
                password_confirmation: this.newPasswordConfirmation
            });
            this.currentPassword = this.newPassword = this.newPasswordConfirmation = '';
            return 'Password updated.';
        });
    }

    startEnable2fa() {
        return this.run(async () => {
            const result = await this.auth.call('POST', '2fa/enable');
            this.mfaSecret = result.secret;
            this.mfaQr = this.sanitizer.bypassSecurityTrustHtml(result.qr_svg);
        });
    }

    confirmEnable2fa() {
        return this.run(async () => {
            const result = await this.auth.action('2fa/confirm', {code: this.mfaCode});
            this.backupCodes = result.backup_codes;
            this.mfaSecret = '';
            this.mfaQr = null;
            this.mfaCode = '';
            await this.auth.updateProfile();
        });
    }

    cancelEnable2fa() {
        this.mfaSecret = '';
        this.mfaQr = null;
        this.mfaCode = '';
    }

    dismissBackupCodes() {
        this.backupCodes = null;
    }

    disable2fa() {
        return this.run(async () => {
            await this.auth.action('2fa/disable', {password: this.disablePassword, code: this.disableCode});
            this.disablePassword = '';
            this.disableCode = '';
            await this.auth.updateProfile();
            return 'Two-factor authentication is disabled.';
        });
    }

    async deleteAccount() {
        if (this.busy) return;
        this.busy = true;
        this.error = '';
        try {
            await this.auth.call('DELETE', 'me', {password: this.deletePassword, confirmation: this.deleteConfirmation});
            this.auth.clear();
            await this.router.navigateByUrl('/login');
        } catch (e) {
            this.error = errorText(e);
        } finally {
            this.busy = false;
        }
    }

    async logout() {
        await this.auth.logout();
    }
}
