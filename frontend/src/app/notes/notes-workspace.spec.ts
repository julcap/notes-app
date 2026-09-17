import {provideHttpClient} from '@angular/common/http';
import {HttpTestingController, provideHttpClientTesting} from '@angular/common/http/testing';
import {ComponentFixture, fakeAsync, flushMicrotasks, TestBed, tick} from '@angular/core/testing';
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

const secondNote: Note = {
    ...note,
    id: 'note-2',
    title: 'Retrospective'
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
        component.query = 'planning';
        const pending = component.load();
        http.expectOne(request => request.url === '/api/notes' && request.params.get('q') === 'planning')
            .flush({}, {status: 503, statusText: 'Unavailable'});

        await pending;
        expect(component.loading).toBeFalse();
        expect(component.error).toContain('Could not load your notes');

        const retry = component.load();
        http.expectOne(request => request.url === '/api/notes' && request.params.get('q') === 'planning')
            .flush({items: [note], total: 1});
        await retry;
        expect(component.error).toBe('');
        expect(component.notes).toEqual([note]);
    });

    it('loads disjoint pages and disables load more when all results are present', async () => {
        fixture.detectChanges();
        const firstRequest = http.expectOne(request => request.url === '/api/notes' && request.params.get('skip') === '0');
        expect(firstRequest.request.params.get('limit')).toBe('50');
        firstRequest.flush({items: [note], total: 2});
        await fixture.whenStable();

        expect(component.total).toBe(2);
        expect(component.hasMore).toBeTrue();

        const more = component.loadMore();
        http.expectOne(request => request.url === '/api/notes' && request.params.get('skip') === '1')
            .flush({items: [secondNote], total: 2});
        await more;

        expect(component.notes).toEqual([note, secondNote]);
        expect(component.hasMore).toBeFalse();
        fixture.detectChanges();
        expect((fixture.nativeElement.querySelector('.load-more') as HTMLButtonElement).disabled).toBeTrue();
    });

    it('debounces server search and finds notes outside the loaded page', fakeAsync(() => {
        component.notes = [note];

        component.queueSearch('retrospective');
        tick(299);
        http.expectNone('/api/notes');
        tick(1);
        const request = http.expectOne(item => item.url === '/api/notes' && item.params.get('q') === 'retrospective');
        expect(request.request.params.get('skip')).toBe('0');
        request.flush({items: [secondNote], total: 1});
        flushMicrotasks();

        expect(component.notes).toEqual([secondNote]);
        expect(component.total).toBe(1);
    }));

    it('ignores a stale search response after the query changes', fakeAsync(() => {
        component.queueSearch('planning');
        tick(300);
        const stale = http.expectOne(item => item.url === '/api/notes' && item.params.get('q') === 'planning');

        component.queueSearch('retrospective');
        stale.flush({items: [note], total: 1});
        flushMicrotasks();
        expect(component.notes).toEqual([]);

        tick(300);
        const current = http.expectOne(item => item.url === '/api/notes' && item.params.get('q') === 'retrospective');
        current.flush({items: [secondNote], total: 1});
        flushMicrotasks();

        expect(component.notes).toEqual([secondNote]);
        expect(component.total).toBe(1);
    }));

    it('does not let an in-flight list response replace a new-note draft', async () => {
        component.selected = note;
        const pending = component.load();
        const request = http.expectOne(item => item.url === '/api/notes');

        component.create();
        expect(component.selected).toBeNull();
        expect(component.editing).toBeTrue();
        request.flush({items: [note], total: 1});
        await pending;

        expect(component.selected).toBeNull();
        expect(component.editing).toBeTrue();
        expect(component.loading).toBeFalse();
    });

    it('does not let an in-flight list response revert a newer card selection', async () => {
        component.notes = [note, secondNote];
        component.selected = note;
        const pending = component.load();
        const request = http.expectOne(item => item.url === '/api/notes');

        component.select(secondNote);
        request.flush({items: [note], total: 1});
        await pending;

        expect(component.selected).toBe(secondNote);
        expect(component.loading).toBeFalse();
    });

    it('keeps a new-note draft open when its server search completes', fakeAsync(() => {
        component.create();
        component.draft.title = 'Unsaved idea';
        component.queueSearch('retrospective');
        tick(300);
        http.expectOne(item => item.url === '/api/notes' && item.params.get('q') === 'retrospective')
            .flush({items: [secondNote], total: 1});
        flushMicrotasks();

        expect(component.selected).toBeNull();
        expect(component.editing).toBeTrue();
        expect(component.draft.title).toBe('Unsaved idea');
        expect(component.notes).toEqual([secondNote]);
    }));

    it('does not load more from the old page while a debounced search is pending', fakeAsync(() => {
        component.notes = [note];
        component.total = 2;
        component.queueSearch('retrospective');

        void component.loadMore();
        tick(299);
        http.expectNone('/api/notes');
        tick(1);
        const request = http.expectOne(item => item.url === '/api/notes' && item.params.get('q') === 'retrospective');
        expect(request.request.params.get('skip')).toBe('0');
        request.flush({items: [secondNote], total: 1});
        flushMicrotasks();
        expect(component.notes).toEqual([secondNote]);
    }));

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
        await Promise.resolve();
        http.expectOne(item => item.url === '/api/notes').flush({items: [note], total: 1});
        await pending;

        expect((component.selected as Note | null)?.id).toBe(note.id);
        expect(component.editing).toBeFalse();
        expect(component.message).toBe('All changes saved');
    });

    it('persists markdown unchanged and renders the saved note', async () => {
        fixture.detectChanges();
        http.expectOne(request => request.url === '/api/notes').flush({items: [], total: 0});
        await fixture.whenStable();
        const content = '## Decision\n\n**Ship it**\n\n- [ ] Tell the team';
        component.selected = null;
        component.editing = true;
        component.draft = {...component.blank(), title: 'Markdown note', content};

        const pending = component.save();
        const request = http.expectOne('/api/notes');
        expect(request.request.body.content).toBe(content);
        request.flush({...note, title: 'Markdown note', content});
        await Promise.resolve();
        http.expectOne(item => item.url === '/api/notes').flush({
            items: [{...note, title: 'Markdown note', content}],
            total: 1
        });
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
        http.expectOne(request => request.url === '/api/notes').flush({items: [{...note, content}], total: 1});
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
        http.expectOne(request => request.url === '/api/notes').flush({items: [], total: 0});
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
        await Promise.resolve();
        http.expectOne(item => item.url === '/api/notes').flush({items: [note], total: 1});
        await pending;

        expect(component.editing).toBeTrue();
        expect(component.draft.title).toBe('Updated planning');
        expect(component.error).toContain('Your draft is still here');
    });

    it('preserves a failed delete error while reconciling pending list work', async () => {
        component.notes = [note];
        component.total = 1;
        component.selected = note;
        component.queueSearch('planning');

        const pending = component.remove();
        http.expectOne('/api/notes/note-1').flush({}, {status: 500, statusText: 'Server Error'});
        await Promise.resolve();
        http.expectOne(item => item.url === '/api/notes' && item.params.get('q') === 'planning')
            .flush({items: [note], total: 1});
        await pending;

        expect(component.selected).toBe(note);
        expect(component.notes).toEqual([note]);
        expect(component.error).toBe('Could not delete the note. Please try again.');
    });

    it('refreshes the server total after create, update, and delete', async () => {
        component.selected = null;
        component.editing = true;
        component.draft = {...component.blank(), title: 'Planning'};
        const create = component.save();
        http.expectOne('/api/notes').flush(note);
        await Promise.resolve();
        http.expectOne(request => request.url === '/api/notes' && request.params.get('skip') === '0')
            .flush({items: [note], total: 1});
        await create;
        expect(component.total).toBe(1);

        component.edit();
        component.draft.title = 'Updated planning';
        const updated = {...note, title: 'Updated planning'};
        const update = component.save();
        http.expectOne('/api/notes/note-1').flush(updated);
        await Promise.resolve();
        http.expectOne(request => request.url === '/api/notes' && request.params.get('skip') === '0')
            .flush({items: [updated], total: 1});
        await update;
        expect(component.total).toBe(1);

        const remove = component.remove();
        http.expectOne('/api/notes/note-1').flush(null);
        await Promise.resolve();
        http.expectOne(request => request.url === '/api/notes' && request.params.get('skip') === '0')
            .flush({items: [], total: 0});
        await remove;
        expect(component.total).toBe(0);
        expect(component.notes).toEqual([]);
    });

    it('keeps a successful save distinct from a failed list refresh', async () => {
        component.selected = null;
        component.editing = true;
        component.draft = {...component.blank(), title: 'Planning'};

        const pending = component.save();
        http.expectOne('/api/notes').flush(note);
        await Promise.resolve();
        http.expectOne(request => request.url === '/api/notes')
            .flush({}, {status: 503, statusText: 'Unavailable'});
        await pending;

        expect(component.editing).toBeFalse();
        expect(component.message).toBe('All changes saved');
        expect(component.error).toContain('Could not load your notes');
        expect(component.error).not.toContain('draft is still here');
    });

    it('keeps a successful delete distinct from a failed list refresh', async () => {
        component.selected = note;
        component.notes = [note];
        component.total = 1;

        const pending = component.remove();
        http.expectOne('/api/notes/note-1').flush(null);
        await Promise.resolve();
        http.expectOne(request => request.url === '/api/notes')
            .flush({}, {status: 503, statusText: 'Unavailable'});
        await pending;

        expect(component.selected).toBeNull();
        expect(component.message).toBe('Note deleted');
        expect(component.error).toContain('Could not load your notes');
        expect(component.error).not.toContain('Could not delete');
    });

    it('does not decrement a filtered total when deleting a retained off-result selection', async () => {
        component.query = 'retrospective';
        component.notes = [secondNote];
        component.total = 1;
        component.selected = note;

        const pending = component.remove();
        http.expectOne('/api/notes/note-1').flush(null);
        await Promise.resolve();
        http.expectOne(request => request.url === '/api/notes' && request.params.get('q') === 'retrospective')
            .flush({}, {status: 503, statusText: 'Unavailable'});
        await pending;

        expect(component.notes).toEqual([secondNote]);
        expect(component.total).toBe(1);
        expect(component.selected).toBe(secondNote);
        expect(component.message).toBe('Note deleted');
    });

    it('does not let an older list response revert an action-item mutation', async () => {
        const item = {
            id: 'item-1',
            text: 'Send recap',
            owner_name: '',
            due_date: null,
            done: false,
            created_at: '2026-09-17T00:00:00Z'
        };
        const mutableNote = {...note, action_items: [item]};
        component.notes = [mutableNote];
        component.total = 1;
        component.selected = mutableNote;
        const oldLoad = component.load();
        const stale = http.expectOne(request => request.url === '/api/notes');

        const mutation = component.toggleActionItem(item);
        http.expectOne('/api/action-items/item-1').flush({...item, done: true});
        await Promise.resolve();
        http.expectOne(request => request.url === '/api/notes')
            .flush({items: [{...mutableNote, action_items: [{...item, done: true}]}], total: 1});
        stale.flush({items: [{...mutableNote, action_items: [{...item, done: false}]}], total: 1});
        await oldLoad;
        await mutation;

        expect(item.done).toBeTrue();
        expect(component.selected?.action_items[0].done).toBeTrue();
        expect(component.notes[0].action_items[0].done).toBeTrue();
    });
});
