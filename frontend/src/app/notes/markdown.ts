import DOMPurify from 'dompurify';
import {Marked} from 'marked';

const allowedTags = [
    'a', 'blockquote', 'br', 'code', 'del', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'hr', 'li', 'ol', 'p', 'pre', 'span', 'strong', 'ul'
];
const allowedAttributes = ['aria-checked', 'class', 'href', 'role', 'title'];
const safeUri = /^(?:(?:https?|mailto):|[#/]|\.\.?\/)/i;

function escapeHtml(value: string) {
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

const markdown = new Marked({gfm: true, breaks: true});
markdown.use({
    renderer: {
        html({text}) {
            return escapeHtml(text);
        },
        image({text}) {
            return escapeHtml(text);
        },
        checkbox({checked}) {
            return `<span class="task-checkbox" role="checkbox" aria-checked="${checked}">${checked ? '☑' : '☐'}</span>`;
        }
    }
});

export function renderMarkdown(source: string) {
    const parsed = markdown.parse(source, {async: false});
    return String(DOMPurify.sanitize(parsed, {
        ALLOWED_ATTR: allowedAttributes,
        ALLOWED_TAGS: allowedTags,
        ALLOWED_URI_REGEXP: safeUri,
        ALLOW_DATA_ATTR: false,
        ALLOW_UNKNOWN_PROTOCOLS: false,
        RETURN_TRUSTED_TYPE: false
    }));
}
