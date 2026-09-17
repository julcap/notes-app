import {Injectable, inject} from '@angular/core';
import {HttpBackend, HttpClient, HttpErrorResponse} from '@angular/common/http';
import {BehaviorSubject, firstValueFrom} from 'rxjs';
import {Router} from '@angular/router';

import {User} from './user.model';

interface Session {
    access_token: string;
    user: User;
}

@Injectable({providedIn: 'root'})
export class AuthService {
    private raw = new HttpClient(inject(HttpBackend));
    private router = inject(Router);
    private subject = new BehaviorSubject<User | null>(null);
    user$ = this.subject.asObservable();

    get user() {
        return this.subject.value;
    }

    token = '';
    private refreshing: Promise<boolean> | null = null;

    headers() {
        const csrf = document.cookie.split('; ').find(x => x.startsWith('minutes_csrf='))?.split('=')[1] || '';
        return {'X-Requested-With': 'Minutes', 'X-CSRF-Token': decodeURIComponent(csrf)};
    }

    accept(session: Session) {
        this.token = session.access_token;
        this.subject.next(session.user);
    }

    async call(method: string, path: string, data: object = {}) {
        const headers = {...this.headers(), ...(this.token ? {Authorization: 'Bearer ' + this.token} : {})};
        const value = await firstValueFrom(this.raw.request<any>(method, '/api/auth/' + path, {body: data, headers}));
        if (value?.access_token) this.accept(value);
        return value;
    }

    async action(path: string, data: object = {}) {
        return this.call('POST', path, data);
    }

    refresh(): Promise<boolean> {
        if (this.refreshing) return this.refreshing;
        this.refreshing = this.action('refresh').then(() => true).catch(() => {
            this.clear();
            return false;
        }).finally(() => this.refreshing = null);
        return this.refreshing;
    }

    async ensure() {
        return !!this.token || await this.refresh();
    }

    clear() {
        this.token = '';
        this.subject.next(null);
    }

    async logout() {
        try {
            await this.action('logout');
        } catch (e) {
            if (!(e instanceof HttpErrorResponse) || e.status !== 401) throw e;
        }
        this.clear();
        await this.router.navigateByUrl('/login');
    }

    async updateProfile() {
        this.subject.next(await firstValueFrom(this.raw.get<User>('/api/auth/me', {headers: {Authorization: 'Bearer ' + this.token}})));
    }
}
