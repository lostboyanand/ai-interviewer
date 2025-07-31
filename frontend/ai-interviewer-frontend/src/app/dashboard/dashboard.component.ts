import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule } from '@angular/forms';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { catchError } from 'rxjs/operators';
import { throwError } from 'rxjs';

interface RegistrationResponse {
  message: string;
  candidate_id: string;
  data: any;
  resume_analysis: any;
  status: string;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css'
})
export class DashboardComponent {
  showModal = false;
  resumeForm: FormGroup;
  selectedFile: File | null = null;
  fileError: string | null = null;
  isSubmitting = false;
  isLoading = false;
  
  constructor(
    private router: Router,
    private fb: FormBuilder,
    private http: HttpClient
  ) {
    this.resumeForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]]
    });
  }

  startInterview() {
    // Open modal instead of navigating directly
    this.showModal = true;
  }

  closeModal() {
    this.showModal = false;
    this.resetForm();
  }

  resetForm() {
    this.resumeForm.reset();
    this.selectedFile = null;
    this.fileError = null;
  }

  onFileSelected(event: any) {
    this.fileError = null;
    const file = event.target.files[0];
    
    // Check if file is selected
    if (!file) {
      this.selectedFile = null;
      return;
    }
    
    // Check file type
    if (file.type !== 'application/pdf') {
      this.fileError = 'Only PDF files are allowed';
      this.selectedFile = null;
      return;
    }
    
    // Check file size (3MB = 3 * 1024 * 1024 bytes)
    if (file.size > 3 * 1024 * 1024) {
      this.fileError = 'File size should not exceed 3MB';
      this.selectedFile = null;
      return;
    }
    
    this.selectedFile = file;
  }

  proceedToInterview() {
    if (this.resumeForm.valid && this.selectedFile && !this.isSubmitting) {
      this.isSubmitting = true;
      this.isLoading = true; // Set loading to true when submission starts
      
      const formData = new FormData();
      formData.append('resume', this.selectedFile);
      formData.append('email', this.resumeForm.get('email')?.value);
      
      // API call to register candidate
      this.http.post<RegistrationResponse>('https://ai-interviewer-1r06.onrender.com/api/register/', formData)
        .pipe(
          catchError(this.handleError)
        )
        .subscribe(
          (response) => {
            console.log('Registration successful:', response);
            
            if (response.status === 'SUCCESS') {
              // Store the candidate data in localStorage/sessionStorage for use in the interview component
              sessionStorage.setItem('candidate_id', response.candidate_id);
              sessionStorage.setItem('candidate_data', JSON.stringify(response.data));
              sessionStorage.setItem('resume_analysis', JSON.stringify(response.resume_analysis));
              
              // Close modal and navigate to interview component after a slight delay for UX
              setTimeout(() => {
                this.isLoading = false; // Reset loading state
                this.closeModal();
                this.router.navigate(['/interview']);
              }, 1500); // Optional delay for better UX
            } else {
              // Handle non-success status
              this.fileError = 'Registration failed: ' + response.message;
              this.isSubmitting = false;
              this.isLoading = false; // Reset loading state
            }
          },
          (error) => {
            console.error('Error during registration:', error);
            this.fileError = 'Failed to register. Please try again.';
            this.isSubmitting = false;
            this.isLoading = false; // Reset loading state
          }
        );
    }
  }

  private handleError(error: HttpErrorResponse) {
    let errorMessage = 'An unknown error occurred!';
    
    if (error.error instanceof ErrorEvent) {
      // Client-side error
      errorMessage = `Error: ${error.error.message}`;
    } else {
      // Server-side error
      errorMessage = `Error Code: ${error.status}\nMessage: ${error.message}`;
    }
    
    console.error(errorMessage);
    return throwError(errorMessage);
  }

  goToAdmin() {
    // Navigate to admin panel
    this.router.navigate(['/hrpanel']);
  }
}