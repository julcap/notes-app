import {provideHttpClient} from '@angular/common/http';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {ComponentFixture, TestBed} from '@angular/core/testing';
import {provideRouter} from '@angular/router';

import {AuthService} from '../auth/auth.service';
import {User} from '../auth/user.model';
import {Note} from './note.model';
import {NotesWorkspace} from './notes-workspace';

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

const note: Note = {
    id: 'note-1',
    title: 'Planning',
    content: 'Decisions',
    attendees: 'Reader',
    meeting_date: '2026-09-17',
    updated_at: '2026-09-17T00:00:00Z',
    attachments: [],
    action_items: []
};

describe('NotesWorkspace', () => {
    let fixture: ComponentFixture<NotesWorkspace>;
    let component: NotesWorkspace;
    let http: HttpTestingController;
    let auth: jasmine.SpyObj<AuthService>;

    beforeEach(async () => {
        auth = jasmine.createSpyObj<AuthService>('AuthService', ['logout', 'action'], {user: {...user}});
        await TestBed.configureTestingModule({
            imports: [NotesWorkspace],
            providers: [
                {provide: AuthService, useValue: auth},
                provideHttpClient(),
                provideHttpClientTesting(),
                provideRouter([])
            ]
        }).compileComponents();
        fixture = TestBed.createComponent(NotesWorkspace);
        component = fixture.componentInstance;
        http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => http.verify());

    it('shows a retryable error when notes cannot be loaded', async () => {
        const pending = component.load();
        http.expectOne('/api/notes').flush({}, {status: 503, statusText: 'Unavailable'});

        await pending;
        expect(component.loading).toBeFalse();
        expect(component.error).toContain('Could not load your notes');
    });

    it('blocks note creation until the email address is verified', () => {
        auth.user!.email_verified = false;

        component.create();

        expect(component.editing).toBeFalse();
        expect(component.error).toBe('Verify your email before creating meeting notes.');
    });

    it('does not submit incomplete create or edit drafts', async () => {
        component.editing = true;
        component.selected = null;
        component.draft = {...component.blank(), title: '   '};
        await component.save();
        http.expectNone('/api/notes');

        component.selected = note;
        component.draft = {...component.fields(note), meeting_date: ''};
        await component.save();
        http.expectNone('/api/notes/note-1');
        expect(component.busy).toBeFalse();
    });

    it('creates a valid meeting note', async () => {
        component.selected = null;
        component.editing = true;
        component.draft = {
            title: 'Planning',
            content: 'Decisions',
            attendees: 'Reader',
            meeting_date: '2026-09-17'
        };

        const pending = component.save();
        const request = http.expectOne('/api/notes');
        expect(request.request.method).toBe('POST');
        expect(request.request.body).toEqual(component.draft);
        request.flush(note);
        await pending;

        expect((component.selected as Note | null)?.id).toBe(note.id);
        expect(component.editing).toBeFalse();
        expect(component.message).toBe('All changes saved');
    });

    it('persists markdown unchanged and renders the saved note', async () => {
        fixture.detectChanges();
        http.expectOne('/api/notes').flush([]);
        await fixture.whenStable();
        const content = '## Decision\n\n**Ship it**\n\n- [ ] Tell the team';
        component.selected = null;
        component.editing = true;
        component.draft = {...component.blank(), title: 'Markdown note', content};

        const pending = component.save();
        const request = http.expectOne('/api/notes');
        expect(request.request.body.content).toBe(content);
        request.flush({...note, title: 'Markdown note', content});
        await pending;
        fixture.detectChanges();

        const body = fixture.nativeElement.querySelector('markdown-renderer.note-body') as HTMLElement;
        expect(body.querySelector('h2')?.textContent).toBe('Decision');
        expect(body.querySelector('strong')?.textContent).toBe('Ship it');
        expect(body.querySelector('[role="checkbox"]')?.getAttribute('aria-checked')).toBe('false');
    });

    it('uses the same sanitized rendering in preview and read mode', async () => {
        const content = '## Decision\n\n**Ship it**\n\n- [x] Told the team';
        fixture.detectChanges();
        http.expectOne('/api/notes').flush([{...note, content}]);
        await fixture.whenStable();
        fixture.detectChanges();
        const readHtml = (fixture.nativeElement.querySelector('.note-body .markdown-content') as HTMLElement).innerHTML;

        component.edit();
        fixture.detectChanges();
        (fixture.nativeElement.querySelector('[aria-label="Preview markdown"]') as HTMLButtonElement).click();
        fixture.detectChanges();
        const previewHtml = (fixture.nativeElement.querySelector('.markdown-preview .markdown-content') as HTMLElement).innerHTML;

        expect(previewHtml).toBe(readHtml);
    });

    it('labels the markdown textarea with the visible Notes label', async () => {
        fixture.detectChanges();
        http.expectOne('/api/notes').flush([]);
        await fixture.whenStable();
        component.create();
        fixture.detectChanges();

        const textarea = fixture.nativeElement.querySelector('markdown-editor textarea') as HTMLTextAreaElement;
        expect(textarea.getAttribute('aria-labelledby')).toBe('content-label');
    });

    it('updates a valid meeting note and preserves the draft after an HTTP error', async () => {
        component.selected = note;
        component.editing = true;
        component.draft = {...component.fields(note), title: 'Updated planning'};

        const pending = component.save();
        const request = http.expectOne('/api/notes/note-1');
        expect(request.request.method).toBe('PUT');
        request.flush({}, {status: 500, statusText: 'Server Error'});
        await pending;

        expect(component.editing).toBeTrue();
        expect(component.draft.title).toBe('Updated planning');
        expect(component.error).toContain('Your draft is still here');
    });
});
