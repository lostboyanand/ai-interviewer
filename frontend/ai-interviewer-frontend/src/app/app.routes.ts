import { Routes } from '@angular/router';
import { DashboardComponent } from './dashboard/dashboard.component';
import { InterviewComponent } from './interview/interview.component';

export const routes: Routes = [
  { path: '', component: DashboardComponent },  // Default route
  { path: 'dashboard', component: DashboardComponent },
  { path: 'interview', component: InterviewComponent },
  // Add more routes as needed
  { path: '**', redirectTo: '' }  // Redirect any unknown routes to dashboard
];