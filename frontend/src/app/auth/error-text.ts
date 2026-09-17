import {HttpErrorResponse} from '@angular/common/http';

export function errorText(e: unknown) {
    if (e instanceof HttpErrorResponse) {
        const d = e.error?.detail;
        return typeof d === 'string' ? d : Array.isArray(d) ? d.map((x: any) => x.msg).join(' ') : 'Could not connect. Please try again.';
    }
    return e instanceof Error ? e.message : 'Please try again.';
}
