import {ComponentFixture, TestBed} from '@angular/core/testing';
import {ActivatedRoute, provideRouter} from '@angular/router';

import {LegalPage} from './legal-page';

describe('LegalPage', () => {
    let fixture: ComponentFixture<LegalPage>;
    const routeData = {document: 'privacy'};

    beforeEach(async () => {
        routeData.document = 'privacy';
        await TestBed.configureTestingModule({
            imports: [LegalPage],
            providers: [
                provideRouter([]),
                {provide: ActivatedRoute, useValue: {snapshot: {data: routeData}}}
            ]
        }).compileComponents();
    });

    function render(document: 'privacy' | 'terms') {
        routeData.document = document;
        fixture = TestBed.createComponent(LegalPage);
        fixture.detectChanges();
        return fixture.nativeElement as HTMLElement;
    }

    it('renders an accessible privacy policy with the implemented data lifecycle', () => {
        const page = render('privacy');
        const text = page.textContent || '';

        expect(page.querySelectorAll('main')).toHaveSize(1);
        expect(page.querySelectorAll('h1')).toHaveSize(1);
        expect(page.querySelector('nav[aria-label="Legal"]')).not.toBeNull();
        expect(text).toContain('Privacy policy');
        expect(text).toContain('15 seconds');
        expect(text).toContain('30 days');
        expect(text).toContain('Account deletion');
        expect(text).toContain('operational backups');
        expect(text).toContain('Sentry');
        expect(text).toContain('Google Fonts');
        expect(text).toContain('Operator and contact details are pending');
    });

    it('renders terms without inventing an operator, jurisdiction, or service promise', () => {
        const page = render('terms');
        const text = page.textContent || '';

        expect(page.querySelectorAll('main')).toHaveSize(1);
        expect(page.querySelectorAll('h1')).toHaveSize(1);
        expect(text).toContain('Terms of service');
        expect(text).toContain('view or edit');
        expect(text).toContain('15-second undo window');
        expect(text).toContain('No service level or support commitment has been published');
        expect(text).toContain('Operator identity, legal contact, governing law, and venue are pending');
        expect(text).toContain('OAuth production approval is still pending');
    });
});
