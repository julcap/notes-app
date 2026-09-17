import {Component, OnInit, HostListener, inject} from '@angular/core';
import {bootstrapApplication} from '@angular/platform-browser';
import {provideHttpClient, HttpClient, withInterceptors} from '@angular/common/http';
import {CommonModule} from '@angular/common';
import {FormsModule} from '@angular/forms';
import {firstValueFrom} from 'rxjs';
import {provideRouter, RouterOutlet, CanDeactivateFn} from '@angular/router';
import {AuthService, authGuard, authInterceptor} from './auth.service';
import {AuthPage} from './auth-pages';

interface Attachment {
    id: string;
    filename: string;
    size: number;
}

interface Note {
    id: string;
    title: string;
    content: string;
    attendees: string;
    meeting_date: string;
    updated_at: string;
    attachments: Attachment[];
}

@Component({
    selector: 'meeting-workspace',
    standalone: true,
    imports: [CommonModule, FormsModule],
    templateUrl: './app.html'
})
export class App implements OnInit {
    private http = inject(HttpClient);
    auth = inject(AuthService);

    async logout() {
        if (this.dirty && !window.confirm('Discard unsaved changes and log out?')) return;
        try {
            this.editing = false;
            await this.auth.logout();
        } catch {
            this.error = 'Could not sign out. Please try again.';
        }
    }

    async resend() {
        try {
            this.message = (await this.auth.action('resend-verification')).message;
        } catch {
            this.error = 'Could not send verification email. Try again later.';
        }
    }

    async downloadFile(a: Attachment) {
        if (!this.selected) return;
        try {
            const blob = await firstValueFrom(this.http.get(`/api/notes/${this.selected.id}/attachments/${a.id}`, {responseType: 'blob'}));
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = a.filename;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch {
            this.error = 'Could not download the attachment. Please try again.';
        }
    }

    notes: Note[] = [];
    selected: Note | null = null;
    draft = this.blank();
    query = '';
    loading = true;
    busy = false;
    editing = false;
    error = '';
    message = '';
    confirmDelete = false;

    blank() {
        const d = new Date();
        return {
            title: '',
            content: '',
            attendees: '',
            meeting_date: new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
        };
    }

    get filtered() {
        const q = this.query.trim().toLowerCase();
        return this.notes.filter(n => `${n.title} ${n.content} ${n.attendees}`.toLowerCase().includes(q));
    }

    get dirty() {
        return this.editing && JSON.stringify(this.draft) !== JSON.stringify(this.selected ? this.fields(this.selected) : this.blank());
    }

    fields(n: Note) {
        return {title: n.title, content: n.content, attendees: n.attendees, meeting_date: n.meeting_date};
    }

    @HostListener('window:beforeunload', ['$event']) unload(e: BeforeUnloadEvent) {
        if (this.dirty) e.preventDefault();
    }

    async ngOnInit() {
        await this.load();
    }

    async load() {
        this.loading = true;
        this.error = '';
        try {
            this.notes = await firstValueFrom(this.http.get<Note[]>('/api/notes'));
            if (!this.selected && this.notes.length) this.select(this.notes[0]);
        } catch {
            this.error = 'Could not load your notes. Check the connection and try again.';
        } finally {
            this.loading = false;
        }
    }

    select(n: Note) {
        if (this.busy || (this.dirty && !window.confirm('Discard unsaved changes?'))) return;
        this.selected = n;
        this.editing = false;
        this.confirmDelete = false;
        this.message = '';
    }

    create() {
        if (!this.auth.user?.email_verified) {
            this.error = 'Verify your email before creating meeting notes.';
            return;
        }
        if (this.busy || (this.dirty && !window.confirm('Discard unsaved changes?'))) return;
        this.selected = null;
        this.draft = this.blank();
        this.editing = true;
        this.confirmDelete = false;
        this.error = '';
    }

    edit() {
        if (this.selected) {
            this.draft = this.fields(this.selected);
            this.editing = true;
        }
    }

    cancel() {
        if (this.dirty && !window.confirm('Discard unsaved changes?')) return;
        this.editing = false;
        if (!this.selected) this.selected = this.notes[0] || null;
    }

    async save() {
        if (!this.draft.title.trim() || !this.draft.meeting_date || this.busy) return;
        this.busy = true;
        this.error = '';
        try {
            const n = await firstValueFrom(this.selected ? this.http.put<Note>('/api/notes/' + this.selected.id, this.draft) : this.http.post<Note>('/api/notes', this.draft));
            this.notes = [n, ...this.notes.filter(x => x.id !== n.id)].sort((a, b) => b.meeting_date.localeCompare(a.meeting_date));
            this.selected = n;
            this.editing = false;
            this.message = 'All changes saved';
        } catch {
            this.error = 'Your note could not be saved. Your draft is still here—please try again.';
        } finally {
            this.busy = false;
        }
    }

    async remove() {
        if (!this.selected || this.busy) return;
        this.busy = true;
        try {
            await firstValueFrom(this.http.delete('/api/notes/' + this.selected.id));
            this.notes = this.notes.filter(n => n.id !== this.selected!.id);
            this.selected = this.notes[0] || null;
            this.confirmDelete = false;
            this.message = 'Note deleted';
        } catch {
            this.error = 'Could not delete the note. Please try again.';
        } finally {
            this.busy = false;
        }
    }

    async upload(event: Event) {
        const input = event.target as HTMLInputElement;
        const file = input.files?.[0];
        if (!file || !this.selected) return;
        if (file.size > 20 * 1024 * 1024) {
            this.error = 'Choose a file no larger than 20 MB.';
            input.value = '';
            return;
        }
        this.busy = true;
        this.error = '';
        const body = new FormData();
        body.append('file', file);
        try {
            const item = await firstValueFrom(this.http.post<Attachment>(`/api/notes/${this.selected.id}/attachments`, body));
            this.selected.attachments.push(item);
            this.message = 'Attachment uploaded';
        } catch {
            this.error = 'Upload failed. Please try again.';
        } finally {
            this.busy = false;
            input.value = '';
        }
    }

    async removeFile(a: Attachment) {
        if (!this.selected || !window.confirm(`Remove ${a.filename}?`)) return;
        this.busy = true;
        try {
            await firstValueFrom(this.http.delete(`/api/notes/${this.selected.id}/attachments/${a.id}`));
            this.selected.attachments = this.selected.attachments.filter(x => x.id !== a.id);
        } catch {
            this.error = 'Could not remove attachment.';
        } finally {
            this.busy = false;
        }
    }
}

const leaveNotes: CanDeactivateFn<App> = component => !component.dirty || window.confirm('Discard unsaved changes?');

@Component({selector: 'app-root', standalone: true, imports: [RouterOutlet], template: '<router-outlet />'})
class Root {
}

bootstrapApplication(Root, {
    providers: [provideHttpClient(withInterceptors([authInterceptor])), provideRouter([
        {path: '', component: App, canActivate: [authGuard], canDeactivate: [leaveNotes]},
        ...[['login', 'login'], ['register', 'register'], ['forgot-password', 'forgot'], ['reset-password', 'reset'], ['verify-email', 'verify'], ['auth/callback', 'callback']].map(([path, mode]) => ({
            path,
            component: AuthPage,
            data: {mode}
        })),
        {path: '**', redirectTo: ''}
    ])]
}).catch(console.error);
