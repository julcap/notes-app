import {Component, ElementRef, EventEmitter, Input, Output, ViewChild} from '@angular/core';

import {MarkdownRenderer} from './markdown-renderer';

@Component({
    selector: 'markdown-editor',
    standalone: true,
    imports: [MarkdownRenderer],
    templateUrl: './markdown-editor.html'
})
export class MarkdownEditor {
    @Input() value = '';
    @Input() labelledBy?: string;
    @Output() readonly valueChange = new EventEmitter<string>();
    @ViewChild('textarea') textarea!: ElementRef<HTMLTextAreaElement>;
    preview = false;

    applyBold() {
        const element = this.textarea.nativeElement;
        const source = element.value;
        const start = element.selectionStart;
        const end = element.selectionEnd;
        const selected = source.slice(start, end) || 'bold text';
        const replacement = `**${selected}**`;
        const nextValue = source.slice(0, start) + replacement + source.slice(end);
        if (nextValue.length > 100000) return;
        this.value = nextValue;
        element.value = this.value;
        element.setSelectionRange(start + 2, start + 2 + selected.length);
        element.focus();
        this.valueChange.emit(this.value);
    }

    applyLine(prefix: string, placeholder: string) {
        const element = this.textarea.nativeElement;
        const source = element.value;
        const lineStart = element.selectionStart === 0
            ? 0
            : source.lastIndexOf('\n', element.selectionStart - 1) + 1;
        const selectionEndsAtNewline = element.selectionEnd > element.selectionStart
            && source[element.selectionEnd - 1] === '\n';
        const nextNewline = source.indexOf('\n', element.selectionEnd);
        const lineEnd = selectionEndsAtNewline
            ? element.selectionEnd - 1
            : nextNewline === -1 ? source.length : nextNewline;
        const block = source.slice(lineStart, lineEnd) || placeholder;
        const replacement = block.split('\n').map(line => prefix + line).join('\n');
        const nextValue = source.slice(0, lineStart) + replacement + source.slice(lineEnd);
        if (nextValue.length > 100000) return;
        this.value = nextValue;
        element.value = this.value;
        element.setSelectionRange(lineStart + prefix.length, lineStart + replacement.length);
        element.focus();
        this.valueChange.emit(this.value);
    }
}
