import {ComponentFixture, TestBed} from '@angular/core/testing';

import {MarkdownEditor} from './markdown-editor';

describe('MarkdownEditor', () => {
    let fixture: ComponentFixture<MarkdownEditor>;
    let component: MarkdownEditor;

    beforeEach(async () => {
        await TestBed.configureTestingModule({imports: [MarkdownEditor]}).compileComponents();
        fixture = TestBed.createComponent(MarkdownEditor);
        component = fixture.componentInstance;
    });

    it('wraps the textarea selection in bold markers and preserves the selection', () => {
        component.value = 'Important decision';
        fixture.detectChanges();
        const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
        textarea.setSelectionRange(0, 9);
        let emitted = '';
        component.valueChange.subscribe(value => emitted = value);

        (fixture.nativeElement.querySelector('[aria-label="Bold"]') as HTMLButtonElement).click();

        expect(emitted).toBe('**Important** decision');
        expect(textarea.selectionStart).toBe(2);
        expect(textarea.selectionEnd).toBe(11);
    });

    it('prefixes every selected line as a heading', () => {
        component.value = 'Decision\nDetails';
        fixture.detectChanges();
        const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
        textarea.setSelectionRange(0, component.value.length);
        let emitted = '';
        component.valueChange.subscribe(value => emitted = value);

        (fixture.nativeElement.querySelector('[aria-label="Heading"]') as HTMLButtonElement).click();

        expect(emitted).toBe('## Decision\n## Details');
        expect(textarea.selectionStart).toBe(3);
        expect(textarea.selectionEnd).toBe(emitted.length);
    });

    it('prefixes every selected line as a bullet list', () => {
        component.value = 'First\nSecond';
        fixture.detectChanges();
        const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
        textarea.setSelectionRange(0, component.value.length);
        let emitted = '';
        component.valueChange.subscribe(value => emitted = value);

        (fixture.nativeElement.querySelector('[aria-label="Bulleted list"]') as HTMLButtonElement).click();

        expect(emitted).toBe('- First\n- Second');
        expect(textarea.selectionStart).toBe(2);
        expect(textarea.selectionEnd).toBe(emitted.length);
    });

    it('does not format the unselected line after a trailing selected newline', () => {
        component.value = 'First\nSecond';
        fixture.detectChanges();
        const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
        textarea.setSelectionRange(0, 6);
        let emitted = '';
        component.valueChange.subscribe(value => emitted = value);

        (fixture.nativeElement.querySelector('[aria-label="Bulleted list"]') as HTMLButtonElement).click();

        expect(emitted).toBe('- First\nSecond');
    });

    it('formats a leading blank line without duplicating its newline', () => {
        component.value = '\nText';
        fixture.detectChanges();
        const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
        textarea.setSelectionRange(0, 0);
        let emitted = '';
        component.valueChange.subscribe(value => emitted = value);

        (fixture.nativeElement.querySelector('[aria-label="Checklist"]') as HTMLButtonElement).click();

        expect(emitted).toBe('- [ ] Action item\nText');
    });

    it('uses browser-normalized line endings for toolbar selection ranges', () => {
        component.value = 'First\r\nSecond';
        fixture.detectChanges();
        const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
        textarea.setSelectionRange(6, 12);
        let emitted = '';
        component.valueChange.subscribe(value => emitted = value);

        (fixture.nativeElement.querySelector('[aria-label="Bulleted list"]') as HTMLButtonElement).click();

        expect(emitted).toBe('First\n- Second');
    });

    it('does not exceed the note content limit through toolbar formatting', () => {
        component.value = 'a'.repeat(100000);
        fixture.detectChanges();
        const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
        textarea.setSelectionRange(0, 1);
        let emitted: string | undefined;
        component.valueChange.subscribe(value => emitted = value);

        (fixture.nativeElement.querySelector('[aria-label="Bold"]') as HTMLButtonElement).click();

        expect(emitted).toBeUndefined();
        expect(textarea.value.length).toBe(100000);
    });

    it('inserts a checkbox placeholder at the caret', () => {
        fixture.detectChanges();
        const textarea = fixture.nativeElement.querySelector('textarea') as HTMLTextAreaElement;
        textarea.setSelectionRange(0, 0);
        let emitted = '';
        component.valueChange.subscribe(value => emitted = value);

        (fixture.nativeElement.querySelector('[aria-label="Checklist"]') as HTMLButtonElement).click();

        expect(emitted).toBe('- [ ] Action item');
        expect(textarea.selectionStart).toBe(6);
        expect(textarea.selectionEnd).toBe(emitted.length);
    });

    it('toggles a sanitized preview of the same markdown value', () => {
        component.value = '# Preview\n\n**Decision**';
        fixture.detectChanges();

        (fixture.nativeElement.querySelector('[aria-label="Preview markdown"]') as HTMLButtonElement).click();
        fixture.detectChanges();

        const preview = fixture.nativeElement.querySelector('markdown-renderer') as HTMLElement;
        expect(fixture.nativeElement.querySelector('textarea')).toBeNull();
        expect(preview.querySelector('h1')?.textContent).toBe('Preview');
        expect(preview.querySelector('strong')?.textContent).toBe('Decision');

        (fixture.nativeElement.querySelector('[aria-label="Edit markdown"]') as HTMLButtonElement).click();
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('textarea')).not.toBeNull();
    });
});
