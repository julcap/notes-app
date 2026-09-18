import {Component, Input, OnChanges} from '@angular/core';

import {renderMarkdown} from './markdown';

@Component({
    selector: 'markdown-renderer',
    standalone: true,
    template: '<div class="markdown-content" [innerHTML]="html"></div>'
})
export class MarkdownRenderer implements OnChanges {
    @Input() source = '';
    html = '';

    ngOnChanges() {
        this.html = renderMarkdown(this.source);
    }
}
