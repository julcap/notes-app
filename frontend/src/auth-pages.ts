import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { AuthService } from './auth.service';
@Component({selector:'auth-page',standalone:true,imports:[CommonModule,FormsModule,RouterLink],templateUrl:'./auth.html'})
export class AuthPage implements OnInit {
 auth=inject(AuthService);private route=inject(ActivatedRoute);private router=inject(Router);private http=inject(HttpClient);
 mode=this.route.snapshot.data['mode'] as string;
 email='';password='';confirmation='';displayName='';remember=false;busy=false;error='';message='';token='';done=false;
 providers:Record<string,boolean>={google:false,facebook:false,amazon:false};
 get title(){return ({login:'Welcome back.',register:'Make room for good ideas.',forgot:'Forgot your password?',reset:'A fresh start.',verify:'Verify your email.',callback:'Signing you in…'} as Record<string,string>)[this.mode];}
 get validPassword(){return this.password.length>=10 && new TextEncoder().encode(this.password).length<=72 && /[a-zA-Z]/.test(this.password) && /[0-9]/.test(this.password);}
 get passwordIssue(){return this.password && !this.validPassword;}
 async ngOnInit(){
  this.token=new URLSearchParams(location.hash.slice(1)).get('token') || '';
  if(this.token)history.replaceState(null,'',location.pathname);
  const error=this.route.snapshot.queryParamMap.get('error');
  if(error)this.error=error==='provider_unavailable'?'This sign-in provider has not been configured yet.':'Social sign-in could not be completed. Try again or use another sign-in method.';
  if(this.mode==='callback'){if(await this.auth.refresh())await this.router.navigateByUrl('/');else this.error='Sign-in failed. Please return to sign in.';}
  if(this.mode==='login'){try{this.providers=await firstValueFrom(this.http.get<Record<string,boolean>>('/api/auth/providers'));}catch{this.error='Could not connect. Please try again.';}}
  if(this.mode==='verify' && !this.token)await this.auth.ensure();
 }
 async submit(){
  if(this.busy)return;
  this.busy=true;this.error='';this.message='';
  try{
   if(this.mode==='register'){
    if(!this.validPassword || this.password!==this.confirmation)throw new Error('Use a password meeting the policy and matching confirmation.');
    await this.auth.action('register',{email:this.email,password:this.password,password_confirmation:this.confirmation,display_name:this.displayName,remember:this.remember});await this.router.navigateByUrl('/');
   }else if(this.mode==='login'){
    await this.auth.action('login',{email:this.email,password:this.password,remember:this.remember});await this.router.navigateByUrl('/');
   }else if(this.mode==='forgot'){
    this.message=(await this.auth.action('forgot-password',{email:this.email})).message;this.done=true;
   }else if(this.mode==='reset'){
    if(!this.validPassword || this.password!==this.confirmation)throw new Error('Use a password meeting the policy and matching confirmation.');
    this.message=(await this.auth.action('reset-password',{token:this.token,password:this.password,password_confirmation:this.confirmation})).message;this.auth.clear();this.done=true;
   }else if(this.mode==='verify'){
    await this.auth.action('verify-email',{token:this.token});this.done=true;this.message='Your email is verified. You can now create meeting notes.';
   }
   this.password='';this.confirmation='';
  }catch(e){this.error=this.errorText(e);}finally{this.busy=false;}
 }
 errorText(e:unknown){if(e instanceof HttpErrorResponse){const d=e.error?.detail;return typeof d==='string'?d:Array.isArray(d)?d.map((x:any)=>x.msg).join(' '):'Could not connect. Please try again.';}return e instanceof Error?e.message:'Please try again.';}
 async resend(){this.busy=true;try{if(!await this.auth.ensure()){await this.router.navigateByUrl('/login');return;}this.message=(await this.auth.action('resend-verification')).message;}catch(e){this.error=this.errorText(e);}finally{this.busy=false;}}
}
