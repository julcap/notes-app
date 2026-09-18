import {Routes} from '@angular/router';

import {authGuard} from './auth/auth.guard';
import {AuthPage} from './auth/auth-page/auth-page';
import {NotesWorkspace, leaveNotesGuard} from './notes/notes-workspace';

const AUTH_PAGES: Array<[path: string, mode: string]> = [
    ['login', 'login'],
    ['register', 'register'],
    ['forgot-password', 'forgot'],
    ['reset-password', 'reset'],
    ['verify-email', 'verify'],
    ['auth/callback', 'callback'],
    ['login-2fa', 'login-2fa'],
];

export const routes: Routes = [
    {path: '', component: NotesWorkspace, canActivate: [authGuard], canDeactivate: [leaveNotesGuard]},
    {path: 'account', loadComponent: () => import('./account/account').then(m => m.Account), canActivate: [authGuard]},
    {path: 'privacy', loadComponent: () => import('./legal/legal-page').then(m => m.LegalPage), data: {document: 'privacy'}},
    {path: 'terms', loadComponent: () => import('./legal/legal-page').then(m => m.LegalPage), data: {document: 'terms'}},
    ...AUTH_PAGES.map(([path, mode]) => ({path, component: AuthPage, data: {mode}})),
    {path: '**', redirectTo: ''},
];
