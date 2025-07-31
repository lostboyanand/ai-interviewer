import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

@Component({
  selector: 'app-hrpanel',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule],
  templateUrl: './hrpanel.component.html',
  styleUrls: ['./hrpanel.component.css']
})
export class HrpanelComponent implements OnInit {
  loginForm: FormGroup;
  jobForm: FormGroup;
  loggedIn = false;
  loading = false;
  loginError = '';
  interviews: any[] = [];
  selectedEmail: string = '';
  selectedInterview: any = null;
  report: any = null;
  loadingReport = false;
  activeSection: string = '';
  showInterviewDetails = false;
  showReportPopup = false;
  showRecommendationsModal = false;
  
  // Smart requirement properties
  jobRecommendations: any = null;
  loadingRecommendations = false;

  constructor(private fb: FormBuilder, private http: HttpClient) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', Validators.required]
    });
    
    this.jobForm = this.fb.group({
      job_title: ['', [Validators.required]],
      job_description: ['', [Validators.required]]
    });
  }

  ngOnInit() {}

  login() {
    this.loading = true;
    this.loginError = '';
    this.http.post<any>('http://localhost:8000/api/hr/login/', this.loginForm.value)
      .subscribe({
        next: (res) => {
          if (res.success) {
            this.loggedIn = true;
            this.fetchInterviews();
          } else {
            this.loginError = res.error || 'Login failed';
          }
          this.loading = false;
        },
        error: (err) => {
          this.loginError = err.error?.error || 'Login failed';
          this.loading = false;
        }
      });
  }

  logout() {
    this.loggedIn = false;
    this.selectedEmail = '';
    this.selectedInterview = null;
    this.report = null;
    this.activeSection = '';
    this.jobRecommendations = null;
  }

  setActiveSection(section: string) {
    this.activeSection = section;
    
    // Reset data when changing sections
    if (section === 'viewReport') {
      this.fetchInterviews();
      this.jobRecommendations = null;
    } else if (section === 'smartRequirement') {
      this.selectedEmail = '';
      this.selectedInterview = null;
      this.report = null;
      // Reset the job form
      this.jobForm.reset();
    } else {
      this.selectedEmail = '';
      this.selectedInterview = null;
      this.report = null;
      this.jobRecommendations = null;
    }
  }

  fetchInterviews() {
    this.http.get<any>('http://localhost:8000/api/interview/responses/')
      .subscribe(res => {
        this.interviews = res.interviews || [];
      });
  }

  onEmailChange() {
    this.selectedInterview = this.interviews.find(i => i.email === this.selectedEmail);
    this.report = null;
    this.showInterviewDetails = !!this.selectedInterview;
  }

  closeInterviewDetails() {
    this.showInterviewDetails = false;
    this.selectedInterview = null;
  }

  viewReport() {
    if (!this.selectedInterview) return;
    this.loadingReport = true;
    this.http.get<any>(`http://localhost:8000/api/interview/report/${this.selectedInterview.interview_id}/`)
      .subscribe({
        next: (res) => {
          this.report = res;
          this.loadingReport = false;
          this.showReportPopup = true;
        },
        error: () => {
          this.report = null;
          this.loadingReport = false;
        }
      });
  }

  closeReportPopup() {
    this.showReportPopup = false;
    this.report = null;
  }

  formatQuestionType(type: string): string {
    if (!type) return '';
    
    // Convert snake_case to Title Case with spaces
    return type
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  downloadReportAsPDF() {
    const reportElement = document.querySelector('.modal-content.xlarge');
    if (!reportElement) return;

    const pdf = new jsPDF('p', 'mm', 'a4');
    pdf.html(reportElement as HTMLElement, {
      callback: (doc) => {
        doc.save(`Interview_Report_${this.selectedInterview?.interview_id || 'report'}.pdf`);
      },
      margin: [10, 10, 10, 10],
      autoPaging: 'text',
      x: 0,
      y: 0,
      width: 190 // fit to A4 width
    });
  }
  
  // Smart Requirement methods
  analyzeJobRequirement() {
  if (this.jobForm.invalid) {
    return;
  }
  
  this.loadingRecommendations = true;
  this.jobRecommendations = null;
  this.showRecommendationsModal = false;
  
  const requestData = {
    job_title: this.jobForm.value.job_title,
    job_description: this.jobForm.value.job_description
  };
  
  this.http.post<any>('http://localhost:8000/api/smart-requirement/', requestData)
    .subscribe({
      next: (response) => {
        this.jobRecommendations = response.recommendations;
        this.loadingRecommendations = false;
        this.showRecommendationsModal = true; // Show modal after loading
      },
      error: (error) => {
        console.error('Error analyzing job requirements:', error);
        this.loadingRecommendations = false;
      }
    });
}

// Add this method
closeRecommendationsModal() {
  this.showRecommendationsModal = false;
}
  
  viewCandidateReport(interviewId: number) {
    this.selectedInterview = { interview_id: interviewId };
    this.viewReport();
  }
}