import {Component, HostListener, inject, OnDestroy, OnInit} from '@angular/core';
import {CommonModule} from '@angular/common';
import {FormsModule} from '@angular/forms';
import {HttpClient} from '@angular/common/http';
import {CanDeactivateFn, RouterLink} from '@angular/router';
import {firstValueFrom} from 'rxjs';

import {AuthService} from '../auth/auth.service';
import {NavRail} from '../shell/nav-rail';
import {ActionItem, Attachment, Note, NotePage} from './note.model';
import {MarkdownEditor} from './markdown-editor';
import {MarkdownRenderer} from './markdown-renderer';

@Component({
    selector: 'meeting-workspace',
    standalone: true,
    imports: [CommonModule, FormsModule, RouterLink, NavRail, MarkdownEditor, MarkdownRenderer],
    templateUrl: './notes-workspace.html'
})
export class NotesWorkspace implements OnInit, OnDestroy {
    private http = inject(HttpClient);
    private requestVersion = 0;
    private searchTimer?: ReturnType<typeof setTimeout>;
    private undoTimer?: ReturnType<typeof setTimeout>;
    auth = inject(AuthService);

    notes: Note[] = [];
    total = 0;
    readonly pageSize = 50;
    selected: Note | null = null;
    draft = this.blank();
    query = '';
    loading = true;
    busy = false;
    editing = false;
    error = '';
    message = '';
    undoNote: Note | null = null;
    newActionItem = this.blankActionItem();

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

    blank() {
        const d = new Date();
        return {
            title: '',
            content: '',
            attendees: '',
            meeting_date: new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
        };
    }

    blankActionItem() {
        return {text: '', owner_name: '', due_date: ''};
    }

    get hasMore() {
        return this.notes.length < this.total;
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

    ngOnDestroy() {
        if (this.searchTimer) clearTimeout(this.searchTimer);
        if (this.undoTimer) clearTimeout(this.undoTimer);
    }

    private invalidateListResponse() {
        this.requestVersion++;
        if (!this.searchTimer) this.loading = false;
    }

    private cancelListWork() {
        this.requestVersion++;
        this.loading = false;
        if (this.searchTimer) {
            clearTimeout(this.searchTimer);
            this.searchTimer = undefined;
        }
    }

    private async restoreListAfterMutation(operationError = '') {
        await this.load();
        if (operationError) this.error = operationError;
    }

    queueSearch(query: string) {
        this.query = query;
        this.requestVersion++;
        if (this.searchTimer) clearTimeout(this.searchTimer);
        this.loading = true;
        this.searchTimer = setTimeout(() => {
            this.searchTimer = undefined;
            void this.load();
        }, 300);
    }

    async load(reset = true) {
        if (this.searchTimer) {
            clearTimeout(this.searchTimer);
            this.searchTimer = undefined;
        }
        const requestVersion = ++this.requestVersion;
        const selectedId = this.selected?.id;
        this.loading = true;
        this.error = '';
        try {
            const page = await firstValueFrom(this.http.get<NotePage>('/api/notes', {
                params: {q: this.query.trim(), skip: reset ? 0 : this.notes.length, limit: this.pageSize}
            }));
            if (requestVersion !== this.requestVersion) return false;
            if (reset) {
                this.notes = page.items;
                if (!selectedId && !this.editing && this.notes.length) this.applySelection(this.notes[0]);
            } else {
                const existing = new Set(this.notes.map(note => note.id));
                this.notes = [...this.notes, ...page.items.filter(note => !existing.has(note.id))];
            }
            this.total = page.total;
            return true;
        } catch {
            if (requestVersion === this.requestVersion) {
                this.error = 'Could not load your notes. Check the connection and try again.';
            }
            return false;
        } finally {
            if (requestVersion === this.requestVersion) this.loading = false;
        }
    }

    async loadMore() {
        if (this.busy || this.loading || !this.hasMore) return;
        await this.load(false);
    }

    private applySelection(note: Note) {
        this.selected = note;
        this.editing = false;
        this.message = '';
        this.newActionItem = this.blankActionItem();
    }

    select(n: Note) {
        if (this.busy || (this.dirty && !window.confirm('Discard unsaved changes?'))) return;
        this.invalidateListResponse();
        this.applySelection(n);
    }

    create() {
        if (!this.auth.user?.email_verified) {
            this.error = 'Verify your email before creating meeting notes.';
            return;
        }
        if (this.busy || (this.dirty && !window.confirm('Discard unsaved changes?'))) return;
        this.invalidateListResponse();
        this.selected = null;
        this.draft = this.blank();
        this.editing = true;
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
        this.cancelListWork();
        let operationError = '';
        this.busy = true;
        this.error = '';
        try {
            const n = await firstValueFrom(this.selected ? this.http.put<Note>('/api/notes/' + this.selected.id, this.draft) : this.http.post<Note>('/api/notes', this.draft));
            this.selected = n;
            this.editing = false;
            this.message = 'All changes saved';
        } catch {
            operationError = 'Your note could not be saved. Your draft is still here—please try again.';
        } finally {
            this.busy = false;
        }
        await this.load();
        if (operationError) this.error = operationError;
    }

    async remove() {
        if (!this.selected || this.busy) return;
        const deletedNote = this.selected;
        const noteId = this.selected.id;
        const undoDeadline = Date.now() + 15_000;
        this.cancelListWork();
        let operationError = '';
        this.busy = true;
        try {
            await firstValueFrom(this.http.delete('/api/notes/' + noteId));
        } catch {
            operationError = 'Could not delete the note. Please try again.';
        } finally {
            this.busy = false;
        }
        if (!operationError) {
            const wasVisible = this.notes.some(note => note.id === noteId);
            this.notes = this.notes.filter(note => note.id !== noteId);
            if (wasVisible) this.total = Math.max(0, this.total - 1);
            this.selected = this.notes[0] || null;
            this.message = 'Note deleted';
            this.showUndo(deletedNote, undoDeadline);
        }
        await this.load();
        if (operationError) this.error = operationError;
    }

    private showUndo(note: Note, deadline: number) {
        this.dismissUndo();
        const remaining = deadline - Date.now();
        if (remaining <= 0) return;
        this.undoNote = note;
        this.undoTimer = setTimeout(() => {
            this.undoNote = null;
            this.undoTimer = undefined;
        }, remaining);
    }

    dismissUndo() {
        if (this.undoTimer) clearTimeout(this.undoTimer);
        this.undoTimer = undefined;
        this.undoNote = null;
    }

    async undoDelete() {
        if (!this.undoNote || this.busy) return;
        const deletedNote = this.undoNote;
        this.cancelListWork();
        let operationError = '';
        this.busy = true;
        this.error = '';
        try {
            const restored = await firstValueFrom(
                this.http.post<Note>(`/api/notes/${deletedNote.id}/undelete`, {})
            );
            this.selected = restored;
            this.message = 'Meeting restored';
        } catch {
            operationError = 'The note could not be restored. The undo window may have expired.';
        } finally {
            this.busy = false;
            this.dismissUndo();
        }
        await this.load();
        if (operationError) this.error = operationError;
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
        this.cancelListWork();
        let operationError = '';
        this.busy = true;
        this.error = '';
        const body = new FormData();
        body.append('file', file);
        try {
            const item = await firstValueFrom(this.http.post<Attachment>(`/api/notes/${this.selected.id}/attachments`, body));
            this.selected.attachments.push(item);
            this.message = 'Attachment uploaded';
        } catch {
            operationError = 'Upload failed. Please try again.';
        } finally {
            this.busy = false;
            input.value = '';
        }
        await this.restoreListAfterMutation(operationError);
    }

    async removeFile(a: Attachment) {
        if (!this.selected || !window.confirm(`Remove ${a.filename}?`)) return;
        this.cancelListWork();
        let operationError = '';
        this.busy = true;
        try {
            await firstValueFrom(this.http.delete(`/api/notes/${this.selected.id}/attachments/${a.id}`));
            this.selected.attachments = this.selected.attachments.filter(x => x.id !== a.id);
        } catch {
            operationError = 'Could not remove attachment.';
        } finally {
            this.busy = false;
        }
        await this.restoreListAfterMutation(operationError);
    }

    async addActionItem() {
        if (!this.selected || !this.newActionItem.text.trim() || this.busy) return;
        this.cancelListWork();
        let operationError = '';
        this.busy = true;
        this.error = '';
        const body = {
            text: this.newActionItem.text.trim(),
            owner_name: this.newActionItem.owner_name.trim(),
            due_date: this.newActionItem.due_date || null
        };
        try {
            const item = await firstValueFrom(this.http.post<ActionItem>(`/api/notes/${this.selected.id}/action-items`, body));
            this.selected.action_items.push(item);
            this.newActionItem = this.blankActionItem();
        } catch {
            operationError = 'Could not add the action item. Please try again.';
        } finally {
            this.busy = false;
        }
        await this.restoreListAfterMutation(operationError);
    }

    async toggleActionItem(item: ActionItem) {
        if (this.busy) return;
        this.cancelListWork();
        let operationError = '';
        this.busy = true;
        try {
            const updated = await firstValueFrom(this.http.patch<ActionItem>(`/api/action-items/${item.id}`, {done: !item.done}));
            item.done = updated.done;
        } catch {
            operationError = 'Could not update the action item.';
        } finally {
            this.busy = false;
        }
        await this.restoreListAfterMutation(operationError);
    }

    async removeActionItem(item: ActionItem) {
        if (!this.selected || this.busy) return;
        this.cancelListWork();
        let operationError = '';
        this.busy = true;
        try {
            await firstValueFrom(this.http.delete(`/api/action-items/${item.id}`));
            this.selected.action_items = this.selected.action_items.filter(x => x.id !== item.id);
        } catch {
            operationError = 'Could not remove the action item.';
        } finally {
            this.busy = false;
        }
        await this.restoreListAfterMutation(operationError);
    }
}

// Component-specific navigation guard, co-located with the component it protects.
export const leaveNotesGuard: CanDeactivateFn<NotesWorkspace> = component => !component.dirty || window.confirm('Discard unsaved changes?');
