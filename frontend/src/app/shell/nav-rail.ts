import {Component, EventEmitter, Input, Output, inject} from '@angular/core';
import {CommonModule} from '@angular/common';
import {RouterLink} from '@angular/router';

import {AuthService} from '../auth/auth.service';

@Component({
    selector: 'nav-rail',
    standalone: true,
    imports: [CommonModule, RouterLink],
    templateUrl: './nav-rail.html'
})
export class NavRail {
    auth = inject(AuthService);
    @Input() active: 'notes' | 'account' = 'notes';
    @Input() notesCount: number | null = null;
    @Output() logoutClick = new EventEmitter<void>();
}
