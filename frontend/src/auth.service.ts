import { Injectable, inject } from '@angular/core';
import { HttpBackend, HttpClient, HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { BehaviorSubject, catchError, firstValueFrom, from, switchMap, throwError } from 'rxjs';
import { CanActivateFn, Router } from '@angular/router';
export interface User { id:number; email:string; display_name:string; email_verified:boolean; auth_provider:string; }
interface Session { access_token:string; user:User; }
@Injectable({providedIn:'root'})
export class AuthService {
  private raw=new HttpClient(inject(HttpBackend));
  private router=inject(Router);
  private subject=new BehaviorSubject<User|null>(null);
  user$=this.subject.asObservable();
  get user(){ return this.subject.value; }
  token='';
  private refreshing:Promise<boolean>|null=null;
  headers(){ const csrf=document.cookie.split('; ').find(x=>x.startsWith('minutes_csrf='))?.split('=')[1] || ''; return {'X-Requested-With':'Minutes','X-CSRF-Token':decodeURIComponent(csrf)}; }
  accept(session:Session){ this.token=session.access_token;this.subject.next(session.user); }
  async action(path:string,data:object={}){ const value=await firstValueFrom(this.raw.post<any>('/api/auth/'+path,data,{headers:{...this.headers(),...(this.token?{Authorization:'Bearer '+this.token}:{})}})); if(value.access_token)this.accept(value);return value; }
  refresh():Promise<boolean>{
    if(this.refreshing)return this.refreshing;
    this.refreshing=this.action('refresh').then(()=>true).catch(()=>{this.clear();return false;}).finally(()=>this.refreshing=null);
    return this.refreshing;
  }
  async ensure(){return !!this.token || await this.refresh();}
  clear(){this.token='';this.subject.next(null);}
  async logout(){try{await this.action('logout');}catch(e){if(!(e instanceof HttpErrorResponse) || e.status!==401)throw e;} this.clear();await this.router.navigateByUrl('/login');}
  async updateProfile(){this.subject.next(await firstValueFrom(this.raw.get<User>('/api/auth/me',{headers:{Authorization:'Bearer '+this.token}})));}
}
export const authGuard:CanActivateFn=async()=>{const auth=inject(AuthService);const router=inject(Router);return await auth.ensure() || router.createUrlTree(['/login']);};
export const authInterceptor:HttpInterceptorFn=(req,next)=>{
 const auth=inject(AuthService);const router=inject(Router);
 if(!req.url.startsWith('/api/notes'))return next(req);
 const authorized=req.clone({setHeaders:{Authorization:'Bearer '+auth.token}});
 return next(authorized).pipe(catchError(error=>{
  if(error.status!==401)return throwError(()=>error);
  return from(auth.refresh()).pipe(switchMap(ok=>{if(!ok){void router.navigateByUrl('/login');return throwError(()=>error);}return next(req.clone({setHeaders:{Authorization:'Bearer '+auth.token}}));}));
 }));
};
