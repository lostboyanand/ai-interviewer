import { Component } from '@angular/core';
import { Router } from '@angular/router';

@Component({
  selector: 'app-dashboard',
  imports: [],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css'
})
export class DashboardComponent {
  constructor(private router: Router) {}

  startInterview() {
    // Navigate to interview page
    this.router.navigate(['/interview']);
  }

  goToAdmin() {
    // Navigate to admin panel
    this.router.navigate(['/admin']);
  }

}
