import {renderMarkdown} from './markdown';

describe('renderMarkdown', () => {
    it('renders supported note formatting and task lists', () => {
        const html = renderMarkdown('# Decisions\n\n**Ship it**\n\n- [x] Tell the team');
        const container = document.createElement('div');
        container.innerHTML = html;
        const checkbox = container.querySelector('[role="checkbox"]');

        expect(html).toContain('<h1>Decisions</h1>');
        expect(html).toContain('<strong>Ship it</strong>');
        expect(checkbox?.getAttribute('aria-checked')).toBe('true');
        expect(checkbox?.textContent).toBe('☑');
    });

    it('preserves single line breaks from existing plain-text notes', () => {
        const html = renderMarkdown('First line\nSecond line');

        expect(html).toContain('First line<br>Second line');
    });

    it('blocks raw HTML, executable URLs, SVG, event handlers, and remote images', () => {
        const attacks = [
            '<script>alert(1)</script>',
            '<img src=x onerror=alert(1)>',
            '[click](javascript:alert(1))',
            '[payload](data:text/html,<script>alert(1)</script>)',
            '<svg><a href="data:text/html,x">x</a></svg>',
            '<div><strong>malformed</div>',
            '<scr<script>ipt>alert(1)</scr<script>ipt>',
            '![tracking pixel](https://tracker.example/pixel.png)'
        ];

        const html = attacks.map(renderMarkdown).join('');
        const container = document.createElement('div');
        container.innerHTML = html;

        expect(container.querySelector('script, img, svg, iframe, object')).toBeNull();
        expect(container.querySelector('[onerror], [onload], [onclick]')).toBeNull();
        expect(Array.from(container.querySelectorAll('[href]')).every(element => {
            const href = element.getAttribute('href') ?? '';
            return !/^(?:javascript|data):/i.test(href);
        })).toBeTrue();
        expect(html).not.toContain('tracker.example');
        expect(container.textContent).toContain('<script>alert(1)</script>');
    });
});
