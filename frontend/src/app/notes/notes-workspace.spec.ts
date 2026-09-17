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
