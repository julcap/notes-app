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
    scheduled_at: null,
    updated_at: '2026-09-17T00:00:00Z',
    attachments: [],
    action_items: [],
    effective_permission: 'owner',
    is_owner: true
};

const secondNote: Note = {
    ...note,
    id: 'note-2',
    title: 'Retrospective'
};

const previewNote: Note = {
    ...note,
    attachments: [
        {id: 'image-1', filename: 'diagram.png', size: 128, content_type: 'image/png'},
        {id: 'pdf-1', filename: 'agenda.pdf', size: 256, content_type: 'application/pdf'},
        {id: 'text-1', filename: 'notes.txt', size: 32, content_type: 'text/plain'}
    ]
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
            meeting_date: '2026-09-17',
            scheduled_at: ''
        };

        const pending = component.save();
        const request = http.expectOne('/api/notes');
        expect(request.request.method).toBe('POST');
        expect(request.request.body).toEqual({...component.draft, scheduled_at: null});
        request.flush(note);
        await Promise.resolve();
        http.expectOne(item => item.url === '/api/notes').flush({items: [note], total: 1});
        await pending;

        expect((component.selected as Note | null)?.id).toBe(note.id);
        expect(component.editing).toBeFalse();
        expect(component.message).toBe('All changes saved');
    });

    it('converts a local scheduled time to UTC before saving', async () => {
        component.selected = null;
        component.editing = true;
        component.draft = {
            ...component.blank(),
            title: 'Scheduled planning',
            scheduled_at: '2026-07-08T01:30'
        };

        const pending = component.save();
        const request = http.expectOne('/api/notes');
        expect(request.request.body.scheduled_at).toBe(new Date('2026-07-08T01:30').toISOString());
        request.flush({...note, title: 'Scheduled planning', scheduled_at: request.request.body.scheduled_at});
        await Promise.resolve();
        http.expectOne(item => item.url === '/api/notes').flush({items: [note], total: 1});
        await pending;
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

    it('renders authenticated image and sandboxed PDF previews while preserving downloads', async () => {
        const createObjectUrl = spyOn(URL, 'createObjectURL').and.callFake(blob => `blob:${(blob as Blob).type}`);
        const click = spyOn(HTMLAnchorElement.prototype, 'click');
        fixture.detectChanges();
        http.expectOne(request => request.url === '/api/notes').flush({items: [previewNote], total: 1});
        await Promise.resolve();

        const image = http.expectOne(request =>
            request.url === '/api/notes/note-1/attachments/image-1' && request.params.get('inline') === 'true'
        );
        const pdf = http.expectOne(request =>
            request.url === '/api/notes/note-1/attachments/pdf-1' && request.params.get('inline') === 'true'
        );
        http.expectNone(request => request.url.includes('/attachments/text-1'));
        image.flush(new Blob(['image'], {type: 'image/png'}), {headers: {'Content-Type': 'image/png'}});
        pdf.flush(new Blob(['pdf'], {type: 'application/pdf'}), {headers: {'Content-Type': 'application/pdf'}});
        await fixture.whenStable();
        fixture.detectChanges();

        const imagePreview = fixture.nativeElement.querySelector('.attachment-preview-image') as HTMLImageElement;
        const pdfPreview = fixture.nativeElement.querySelector('.attachment-preview-pdf') as HTMLIFrameElement;
        expect(imagePreview.src).toContain('blob:image/png');
        expect(pdfPreview.src).toContain('blob:application/pdf');
        expect(pdfPreview.getAttribute('sandbox')).toBe('');
        expect(fixture.nativeElement.querySelectorAll('[aria-label^="Download "]').length).toBe(3);
        expect(createObjectUrl).toHaveBeenCalledTimes(2);

        (fixture.nativeElement.querySelector('[aria-label="Download diagram.png"]') as HTMLButtonElement).click();
        const download = http.expectOne(request =>
            request.url === '/api/notes/note-1/attachments/image-1' && !request.params.has('inline')
        );
        download.flush(new Blob(['image'], {type: 'application/octet-stream'}));
        await fixture.whenStable();
        expect(click).toHaveBeenCalled();
    });

    it('rejects download-only preview responses and revokes preview URLs on selection and destroy', async () => {
        const createObjectUrl = spyOn(URL, 'createObjectURL').and.callFake(blob => `blob:${(blob as Blob).type}`);
        const revokeObjectUrl = spyOn(URL, 'revokeObjectURL');
        fixture.detectChanges();
        http.expectOne(request => request.url === '/api/notes').flush({items: [previewNote, secondNote], total: 2});
        await Promise.resolve();
        http.expectOne(request => request.url.endsWith('/attachments/image-1'))
            .flush(new Blob(['image'], {type: 'image/png'}));
        http.expectOne(request => request.url.endsWith('/attachments/pdf-1'))
            .flush(new Blob(['pdf'], {type: 'application/octet-stream'}));
        await fixture.whenStable();
        fixture.detectChanges();

        expect(createObjectUrl).toHaveBeenCalledTimes(1);
        expect(fixture.nativeElement.querySelector('.attachment-preview-image')).not.toBeNull();
        expect(fixture.nativeElement.querySelector('.attachment-preview-pdf')).toBeNull();

        component.select(secondNote);
        expect(revokeObjectUrl).toHaveBeenCalledOnceWith('blob:image/png');

        component.select(previewNote);
        http.expectOne(request => request.url.endsWith('/attachments/image-1'))
            .flush(new Blob(['image'], {type: 'image/png'}));
        http.expectOne(request => request.url.endsWith('/attachments/pdf-1'))
            .flush(new Blob(['pdf'], {type: 'application/pdf'}));
        await fixture.whenStable();
        fixture.destroy();

        expect(revokeObjectUrl).toHaveBeenCalledWith('blob:image/png');
        expect(revokeObjectUrl).toHaveBeenCalledWith('blob:application/pdf');
    });

    it('downloads authenticated Markdown and PDF exports with server-provided filenames', fakeAsync(() => {
        const createObjectUrl = spyOn(URL, 'createObjectURL').and.returnValues('blob:markdown', 'blob:pdf');
        const revokeObjectUrl = spyOn(URL, 'revokeObjectURL');
        const downloads: string[] = [];
        spyOn(HTMLAnchorElement.prototype, 'click').and.callFake(function (this: HTMLAnchorElement) {
            downloads.push(this.download);
        });
        fixture.detectChanges();
        http.expectOne(request => request.url === '/api/notes').flush({items: [note], total: 1});
        flushMicrotasks();
        fixture.detectChanges();

        const buttons = Array.from(
            fixture.nativeElement.querySelectorAll('[data-export-format]') as NodeListOf<HTMLButtonElement>
        );
        expect(buttons.map(button => button.textContent?.trim())).toEqual(['Export Markdown', 'Export PDF']);

        buttons[0].click();
        const markdown = http.expectOne(request =>
            request.url === '/api/notes/note-1/export' && request.params.get('format') === 'md'
        );
        expect(markdown.request.responseType).toBe('blob');
        markdown.flush(new Blob(['# Planning'], {type: 'text/markdown'}), {
            headers: {'Content-Disposition': 'attachment; filename="Planning.md"'}
        });
        flushMicrotasks();

        buttons[1].click();
        const pdf = http.expectOne(request =>
            request.url === '/api/notes/note-1/export' && request.params.get('format') === 'pdf'
        );
        expect(pdf.request.responseType).toBe('blob');
        pdf.flush(new Blob(['pdf'], {type: 'application/pdf'}), {
            headers: {'Content-Disposition': 'attachment; filename="Planning.pdf"'}
        });
        flushMicrotasks();

        expect(downloads).toEqual(['Planning.md', 'Planning.pdf']);
        expect(createObjectUrl).toHaveBeenCalledTimes(2);
        tick(1000);
        expect(revokeObjectUrl).toHaveBeenCalledWith('blob:markdown');
        expect(revokeObjectUrl).toHaveBeenCalledWith('blob:pdf');
    }));

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

    it('shows a 15-second undo toast after deleting a note', fakeAsync(() => {
        fixture.detectChanges();
        http.expectOne(request => request.url === '/api/notes').flush({items: [], total: 0});
        flushMicrotasks();
        component.notes = [note, secondNote];
        component.total = 2;
        component.selected = note;

        void component.remove();
        http.expectOne('/api/notes/note-1').flush(null);
        flushMicrotasks();
        http.expectOne(request => request.url === '/api/notes').flush({items: [secondNote], total: 1});
        flushMicrotasks();
        fixture.detectChanges();

        const toast = fixture.nativeElement.querySelector('.undo-toast') as HTMLElement;
        expect(toast.textContent).toContain('Meeting deleted');
        expect(toast.textContent).toContain('Undo');
        expect(component.total).toBe(1);
        expect(component.notes).toEqual([secondNote]);

        tick(14_999);
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('.undo-toast')).not.toBeNull();
        tick(1);
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('.undo-toast')).toBeNull();
    }));

    it('does not offer undo after a delayed delete response consumes the server window', fakeAsync(() => {
        fixture.detectChanges();
        http.expectOne(request => request.url === '/api/notes').flush({items: [], total: 0});
        flushMicrotasks();
        component.notes = [note];
        component.total = 1;
        component.selected = note;

        void component.remove();
        const deletion = http.expectOne('/api/notes/note-1');
        tick(15_000);
        deletion.flush(null);
        flushMicrotasks();
        http.expectOne(request => request.url === '/api/notes').flush({items: [], total: 0});
        flushMicrotasks();
        fixture.detectChanges();

        expect(component.undoNote).toBeNull();
        expect(fixture.nativeElement.querySelector('.undo-toast')).toBeNull();
    }));

    it('restores a deleted note and authoritative paginated total when undo is pressed', fakeAsync(() => {
        fixture.detectChanges();
        http.expectOne(request => request.url === '/api/notes').flush({items: [], total: 0});
        flushMicrotasks();
        component.notes = [note];
        component.total = 1;
        component.selected = note;

        void component.remove();
        http.expectOne('/api/notes/note-1').flush(null);
        flushMicrotasks();
        http.expectOne(request => request.url === '/api/notes').flush({items: [], total: 0});
        flushMicrotasks();

        void component.undoDelete();
        const undo = http.expectOne('/api/notes/note-1/undelete');
        expect(undo.request.method).toBe('POST');
        undo.flush(note);
        flushMicrotasks();
        http.expectOne(request => request.url === '/api/notes' && request.params.get('skip') === '0')
            .flush({items: [note], total: 1});
        flushMicrotasks();

        expect(component.selected).toBe(note);
        expect(component.notes).toEqual([note]);
        expect(component.total).toBe(1);
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('.undo-toast')).toBeNull();
    }));

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

    it('shows shared badges and hides every write affordance from view-only collaborators', () => {
        const shared = {...note, effective_permission: 'view', is_owner: false} as Note;
        component.notes = [shared];
        component.selected = shared;
        fixture.detectChanges();
        http.expectOne(request => request.url === '/api/notes').flush({items: [shared], total: 1});

        expect(fixture.nativeElement.textContent).toContain('Shared · view');
        expect(fixture.nativeElement.querySelector('[data-action="edit-note"]')).toBeNull();
        expect(fixture.nativeElement.querySelector('[data-action="delete-note"]')).toBeNull();
        expect(fixture.nativeElement.querySelector('[data-action="share-note"]')).toBeNull();
        expect(fixture.nativeElement.querySelector('input[aria-label="Upload attachment"]')).toBeNull();
        expect(fixture.nativeElement.querySelector('.action-item-form')).toBeNull();
    });

    it('allows edit collaborators to edit content and children without owner-only controls', () => {
        const shared = {...note, effective_permission: 'edit', is_owner: false} as Note;
        component.notes = [shared];
        component.selected = shared;
        fixture.detectChanges();
        http.expectOne(request => request.url === '/api/notes').flush({items: [shared], total: 1});

        expect(fixture.nativeElement.querySelector('[data-action="edit-note"]')).not.toBeNull();
        expect(fixture.nativeElement.querySelector('[data-action="delete-note"]')).toBeNull();
        expect(fixture.nativeElement.querySelector('[data-action="share-note"]')).toBeNull();
        expect(fixture.nativeElement.querySelector('input[aria-label="Upload attachment"]')).not.toBeNull();
        expect(fixture.nativeElement.querySelector('.action-item-form')).not.toBeNull();
    });

    it('loads collaborators and previous contacts before explicit bulk sharing', async () => {
        const owned = {...note, effective_permission: 'owner', is_owner: true} as Note;
        component.notes = [owned];
        component.selected = owned;

        const opening = component.openSharing();
        http.expectOne('/api/notes/note-1/shares').flush([
            {user_id: 2, email: 'viewer@example.com', display_name: 'Viewer', permission: 'view', shared_at: '2026-09-18T00:00:00Z'}
        ]);
        http.expectOne('/api/sharing/contacts').flush([
            {user_id: 2, email: 'viewer@example.com', display_name: 'Viewer'}
        ]);
        await opening;
        expect(component.sharingOpen).toBeTrue();
        expect(component.shares.length).toBe(1);
        expect(component.sharingContacts.length).toBe(1);

        spyOn(window, 'confirm').and.returnValue(true);
        const bulk = component.shareWithPrevious();
        const request = http.expectOne('/api/notes/note-1/shares/previous');
        expect(request.request.method).toBe('POST');
        expect(request.request.body).toEqual({permission: 'view', user_ids: [2]});
        request.flush(component.shares);
        await bulk;
        expect(window.confirm).toHaveBeenCalledWith('Share with viewer@example.com?');
    });

    it('discards stale sharing responses after selecting another note', async () => {
        const first = {...note, effective_permission: 'owner', is_owner: true} as Note;
        const second = {...first, id: 'note-2', title: 'Second'} as Note;
        component.notes = [first, second];
        component.selected = first;

        const opening = component.openSharing();
        const staleShares = http.expectOne('/api/notes/note-1/shares');
        const staleContacts = http.expectOne('/api/sharing/contacts');
        component.select(second);
        staleShares.flush([
            {user_id: 2, email: 'viewer@example.com', display_name: 'Viewer', permission: 'view', shared_at: '2026-09-18T00:00:00Z'}
        ]);
        staleContacts.flush([{user_id: 2, email: 'viewer@example.com', display_name: 'Viewer'}]);
        await opening;

        expect(component.selected?.id).toBe('note-2');
        expect(component.sharingOpen).toBeFalse();
        expect(component.shares).toEqual([]);
        expect(component.sharingContacts).toEqual([]);
    });

    it('clears sharing state when creating a new note', () => {
        component.selected = {...note, effective_permission: 'owner', is_owner: true} as Note;
        component.sharingOpen = true;
        component.shares = [
            {user_id: 2, email: 'viewer@example.com', display_name: 'Viewer', permission: 'view', shared_at: '2026-09-18T00:00:00Z'}
        ];
        component.sharingContacts = [{user_id: 2, email: 'viewer@example.com', display_name: 'Viewer'}];

        component.create();

        expect(component.selected).toBeNull();
        expect(component.sharingOpen).toBeFalse();
        expect(component.shares).toEqual([]);
        expect(component.sharingContacts).toEqual([]);
    });
});
