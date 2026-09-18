import {CommonModule} from '@angular/common';
import {Component, inject} from '@angular/core';
import {ActivatedRoute, RouterLink} from '@angular/router';

@Component({
    selector: 'legal-page',
    standalone: true,
    imports: [CommonModule, RouterLink],
    templateUrl: './legal-page.html',
    styleUrl: './legal-page.scss'
})
export class LegalPage {
    private route = inject(ActivatedRoute);
    document = this.route.snapshot.data['document'] as 'privacy' | 'terms';

    get isPrivacy() {
        return this.document === 'privacy';
    }
}
