import { Routes ,  RouterModule } from '@angular/router';
import { NgModule } from '@angular/core';
import {DashboardComponent} from './dashboard/dashboard.component';

export const routes: Routes = [
    { path: '', component: DashboardComponent },  // Default route
    { path: 'dashboard', component: DashboardComponent },
    // Add more routes as needed
    { path: '**', redirectTo: '' }  // Redirect any unknown routes to dashboard
  ];
  
  @NgModule({
    imports: [RouterModule.forRoot(routes)],
    exports: [RouterModule]
  })
  export class AppRoutingModule { }
