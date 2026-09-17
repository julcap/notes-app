import {inject} from '@angular/core';
import {HttpInterceptorFn} from '@angular/common/http';
import {Router} from '@angular/router';
import {catchError, from, switchMap, throwError} from 'rxjs';

import {AuthService} from './auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
    const auth = inject(AuthService);
    const router = inject(Router);
    if (!req.url.startsWith('/api/notes')) return next(req);
    const authorized = req.clone({setHeaders: {Authorization: 'Bearer ' + auth.token}});
    return next(authorized).pipe(catchError(error => {
        if (error.status !== 401) return throwError(() => error);
        return from(auth.refresh()).pipe(switchMap(ok => {
            if (!ok) {
                void router.navigateByUrl('/login');
                return throwError(() => error);
            }
            return next(req.clone({setHeaders: {Authorization: 'Bearer ' + auth.token}}));
        }));
    }));
};
